import socket
import threading
import queue
import random

MULTICAST_ADDR = '224.0.0.10'
MULTICAST_PORT = 49152

MAX_INCOMING = 5
MAX_OUTGOING = 5

# IP helper function - https://stackoverflow.com/a/28950776
def get_machine_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class PeerNotifier:
    def __init__(self, local_ip):
        self.local_ip = local_ip
        self.cast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.notifs = queue.Queue(10)
        self._configure_cast_sock()
        self.cast_listen_thread = None
        self.start_listen()

    def _configure_cast_sock(self):
        self.cast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.cast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self.cast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(MULTICAST_ADDR) + socket.inet_aton("0.0.0.0"))
        self.cast_sock.bind(('0.0.0.0', BROADCAST_PORT))

    def cast(self, message):
        self.cast_sock.sendto(message.encode(), (MULTICAST_ADDR, MULTICAST_PORT))
        print('Multicasting:', message)

    def start_listen(self):

        def _listen_cast():
            while True:
                data, sender = self.cast_sock.recvfrom(1024)
                sender_addr, sender_port = sender
                if sender_addr == self.local_ip:
                    if data == 'stop':
                        print('Received stop signal')
                        break
                    print(f'Ignoring broadcast message from {sender_addr}')
                else:
                    print(sender_addr, 'multicast:', data)
                    self.notifs.put((data, sender_addr, sender_port))

        self.cast_listen_thread = threading.Thread(target=_listen_cast)
        self.cast_listen_thread.start()

    def stop_listen(self):
        self.cast_sock.sendto('stop'.encode(), (self.local_ip, MULTICAST_PORT))
        print('Sending signal to stop local listening to multicast')
        self.cast_listen_thread.join()

    def close(self):
        if self.cast_listen_thread.is_alive():
            self.stop_listen()
        self.notifs.put('stop')
        self.cast_sock.close()


class LocalNode:
    def __init__(self, num_in, num_out):
        # Get the local IP through the default device
        self.local_ip = get_machine_ip()
        # Max connections
        self.max_served = num_in
        self.max_connect = num_out
        # UDP/Peer searching
        self.peers = PeerNotifier(self.local_ip)
        self.peer_aware = True
        # Thread locks
        self.serv_conn_lock = threading.Lock()
        self.client_conn_lock = threading.Lock()
        self.ports_lock = threading.Lock()
        # Thread containers
        self.peer_notif_cb_thread = None
        self.serv_manager_thread = None
        # Store ports to broadcast availability
        self.available_ports = set()
        # Store ports used across the servers and clients
        self.used_ports = set()
        # Store IPs and connected sockets
        self.served_connections = dict()
        self.client_connections = dict()
        # Queues for event handling
        self.remote_action_q = queue.Queue(num_in + num_out)

    def _peer_notif_handler(self):

        def _make_callbacks():
            client_threads = []
            while True:
                new_notif = self.peers.notifs.get()
                if new_notif == 'stop': break
                if self.peer_aware:
                    command, send_addr, send_port = new_notif
                    command_op, command_args = command.split(' ')
                    if command_op == 'available':
                        if not type(args) == str: continue
                        t = threading.Thread(target=self.new_client, args=(send_addr, command_args))
                        t.start()
                        client_threads.append(t)
            for t in client_threads:
                t.join()

        self.peer_notif_cb_thread = threading.Thread(target=_make_callbacks)
        self.peer_notif_cb_thread.start()

    def _stop_peer_notif(self):
        self.peers.close()
        self.peer_notif_cb_thread.join()

    def _generate_port(self):
        # Generate range from just above MULTICAST_PORT to maximum port range
        random_port = random.randint(MULTICAST_PORT + 1, 65535)
        self.ports_lock.acquire()
        while random_port in self.available_ports or random_port in self.used_ports:
            random_port = random.randint(MULTICAST_PORT + 1, 65535)
        self.ports_lock.release()
        return random_port

    def manage_servers(self):

        def _manage_threads():
            server_threads = []
            while True:
                if len(self.available_ports) + len(self.served_connections) < self.max_served:
                    new_port = self._generate_port()
                    t = threading.Thread(target=self.new_serv, args=(new_port,))
                    t.start()
                    server_threads.append(t)
                # TODO: break condition
            for t in server_threads:
                t.join()

    def new_serv(self, port):
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_sock.bind(('0.0.0.0', port))
        tcp_sock.listen()
        self.ports_lock.acquire()
        while True:
            self.available_ports.add(port)
            self.ports_lock.release()
            client_conn, client_addr = tcp_sock.accept()
            self.ports_lock.acquire()
            self.available_ports.remove(port)
            self.used_ports.add(port)
            self.ports_lock.release()
            self.serv_conn_lock.acquire()
            self.served_connections[client_addr] = client_conn
            self.serv_conn_lock.release()
            with client_conn:
                print(client_addr, 'connected to server port', port)
                while True:
                    data = conn.recvfrom(1024)
                    if not data: break
                    self.remote_action_q.put(data)
                self.serv_conn_lock.acquire()
                self.served_connections.pop(client_addr)
                self.serv_conn_lock.release()
            self.ports_lock.acquire()
            self.used_ports.remove(port)

    def new_client(self, addr, port):
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with client_sock:
            try:
                self.ports_lock.acquire()
                self.used_ports.add(port)
                self.ports_lock.release()
                client_sock.connect((addr, port))
                print('Client connected to', addr, 'port', port)
                self.client_conn_lock.acquire()
                self.client_connections[addr] = client_sock
                self.client_conn_lock.release()
                while True:
                    data = connect_sock.recvfrom(1024)
                    if not data: break
                    self.remote_action_q.put(data)
            except ConnectionRefusedError as e:
                print('Error:', e, ', aborting connection')
            finally:
                self.client_conn_lock.acquire()
                self.client_connections.pop(addr)
                self.client_conn_lock.release()
                self.ports_lock.acquire()
                self.used_ports.remove(port)
                self.ports_lock.release()



