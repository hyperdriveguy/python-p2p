import socket
import threading
import queue
import random
from time import sleep
from itertools import chain

MULTICAST_ADDR = '224.0.0.10'
MULTICAST_PORT = 49152

MAX_INCOMING = 5
MAX_OUTGOING = 5

ADVERTISE_SERV_DELAY = 3

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
        self.cast_sock.bind(('0.0.0.0', MULTICAST_PORT))

    def cast(self, message):
        try:
            self.cast_sock.sendto(message.encode(), (MULTICAST_ADDR, MULTICAST_PORT))
            print('Multicasting:', message)
        except OSError as e:
            print('Error, unable to cast message:', e)

    def start_listen(self):

        def _listen_cast():
            while True:
                data, sender = self.cast_sock.recvfrom(1024)
                sender_addr, sender_port = sender
                if sender_addr == self.local_ip:
                    if data == b'stop':
                        print('Received stop signal')
                        self.notifs.put('stop')
                        break
                    else:
                        print(f'Ignoring broadcast message from {sender_addr}')
                else:
                    print(sender_addr, 'multicast:', data)
                    self.notifs.put((data.decode(), sender_addr, sender_port))

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
        # Signals
        self.server_manager_signal = threading.Semaphore(1)
        self.stop_advertiser = False
        self.stop_serv = False
        # Thread containers
        self.peer_notif_cb_thread = None
        self.serv_manager_thread = None
        self.propogate_data_thread = None
        self.advertise_thread = None
        # Store ports to broadcast availability
        self.available_ports = dict()
        # Store ports used across the servers and clients
        self.used_ports = dict()
        # Store IPs and connected sockets
        self.served_connections = dict()
        self.client_connections = dict()
        # Queues for event handling on local node and sending to other nodes
        self.data_propogate_queue = queue.Queue(num_in + num_out)
        self.local_data_queue = queue.Queue((num_in + num_out)*2)

        # Start handlers
        self._peer_notif_handler()
        self._manage_servers()
        self._propogate_data()

    def _peer_notif_handler(self):

        def _make_callbacks():
            client_threads = []
            while True:
                new_notif = self.peers.notifs.get()
                if new_notif == 'stop':
                    self.stop_advertiser = True
                    break
                elif self.peer_aware:
                    command, send_addr, send_port = new_notif
                    command_op, command_args = command.split(' ')
                    if command_op == 'available':
                        if not type(command_args) == str: continue
                        self.serv_conn_lock.acquire()
                        self.client_conn_lock.acquire()
                        if send_addr in self.served_connections.keys() or send_addr in self.client_connections.keys(): continue
                        self.serv_conn_lock.release()
                        self.client_conn_lock.release()
                        t = threading.Thread(target=self.new_client, args=(send_addr, int(command_args)))
                        t.start()
                        client_threads.append(t)
            for t in client_threads:
                t.join()

        self.peer_notif_cb_thread = threading.Thread(target=_make_callbacks)
        self.peer_notif_cb_thread.start()

    def _shutdown_sockets(self):
        for conn in chain(self.available_ports.values(), self.used_ports.values()):
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()

    def _stop_peer_notif(self):
        self.peers.close()
        self.peer_notif_cb_thread.join()

    def _generate_port(self):
        # Generate range from just above MULTICAST_PORT to maximum port range
        random_port = random.randint(MULTICAST_PORT + 1, 65535)
        self.ports_lock.acquire()
        while random_port in self.available_ports.keys() or random_port in self.used_ports.keys():
            random_port = random.randint(MULTICAST_PORT + 1, 65535)
        self.ports_lock.release()
        return random_port

    def _manage_servers(self):

        def _manage_threads():
            server_threads = []
            while len(self.available_ports) + len(self.served_connections) < self.max_served:
                self.server_manager_signal.acquire()
                if self.stop_serv: break
                new_port = self._generate_port()
                t = threading.Thread(target=self.new_serv, args=(new_port,))
                t.start()
                server_threads.append(t)
            for t in server_threads:
                t.join()

        def _advertise_servers():
            while True:
                self.ports_lock.acquire()
                print(self.stop_advertiser)
                for port in self.available_ports.keys():
                    self.peers.cast(f'available {port}')
                self.ports_lock.release()
                sleep(ADVERTISE_SERV_DELAY)
                if self.stop_advertiser: break

        self.serv_manager_thread = threading.Thread(target=_manage_threads)
        self.advertise_thread = threading.Thread(target=_advertise_servers)
        self.serv_manager_thread.start()
        self.advertise_thread.start()

    def _stop_server_manager(self):
        self.stop_serv = True
        self.stop_advertiser = True
        self.server_manager_signal.release()
        self.advertise_thread.join()
        self.serv_manager_thread.join()

    def data_spread(self, data, origin=None):
        for addr, conn in chain(self.served_connections.items(), self.client_connections.items()):
            if addr == origin: continue
            try:
                conn.send(data.encode())
            except BrokenPipeError:
                pass
    
    def _propogate_data(self):

        def _queue_listener():
            while True:
                origin_addr, new_data = self.data_propogate_queue.get()
                if origin_addr is None and new_data == 'stop': break
                if new_data[0] == b'': continue
                self.data_spread(new_data, origin_addr)
                self.local_data_queue.put(new_data)
        
        self.propogate_data_thread = threading.Thread(target=_queue_listener)
        self.propogate_data_thread.start()
    
    def _stop_data_propogator(self):
        self.data_propogate_queue.put((None, 'stop'))
        self.propogate_data_thread.join()

    def close(self):
        self._shutdown_sockets()
        self._stop_peer_notif()
        self._stop_server_manager()
        self._stop_data_propogator()

    def new_serv(self, port):
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_sock.bind(('0.0.0.0', port))
        tcp_sock.listen()
        self.ports_lock.acquire()
        while True:
            self.available_ports[port] = tcp_sock
            self.ports_lock.release()
            try:
                client_conn, client_full_addr = tcp_sock.accept()
                client_addr, client_port = client_full_addr
            except OSError as e:
                print('Error accepting client:', e)
                tcp_sock.close()
                break
            self.server_manager_signal.release()
            self.ports_lock.acquire()
            self.available_ports.pop(port)
            self.used_ports[port] = tcp_sock
            self.ports_lock.release()
            self.serv_conn_lock.acquire()
            self.served_connections[client_addr] = client_conn
            self.serv_conn_lock.release()
            with client_conn:
                print(client_addr, 'connected to server port', port)
                while True:
                    data = client_conn.recvfrom(1024)
                    if not data: break
                    self.data_propogate_queue.put((client_addr, data))
                self.serv_conn_lock.acquire()
                self.served_connections.pop(client_addr)
                self.serv_conn_lock.release()
            self.ports_lock.acquire()
            self.used_ports.pop(port)

    def new_client(self, addr, port:int):
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with client_sock:
            try:
                self.ports_lock.acquire()
                self.used_ports[port] = client_sock
                self.ports_lock.release()
                client_sock.connect((addr, port))
                print('Client connected to', addr, 'port', port)
                self.client_conn_lock.acquire()
                self.client_connections[addr] = client_sock
                self.client_conn_lock.release()
                while True:
                    try:
                        data = client_sock.recvfrom(1024)
                    except OSError as e:
                        print('Error recieving data:', e)
                        break
                    if not data: break
                    self.data_propogate_queue.put((addr, data))
            except ConnectionRefusedError as e:
                print('Error:', e, ', aborting connection')
            finally:
                self.client_conn_lock.acquire()
                self.client_connections.pop(addr)
                self.client_conn_lock.release()
                self.ports_lock.acquire()
                self.used_ports.pop(port)
                self.ports_lock.release()


if __name__ == '__main__':
    local_node = LocalNode(MAX_INCOMING, MAX_OUTGOING)
    sleep(5)
    # def bruh():
    #     while True:
    #         local_node.data_spread('your mom')
    #         sleep(random.randint(1, 5))
    #
    # bruh_t = threading.Thread(target=bruh)
    # bruh_t.start()
    # for _ in range(500):
    #     print('Data:', local_node.local_data_queue.get())
    # bruh_t.join()
    local_node.close()

