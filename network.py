import socket
import threading
import queue

MULTICAST_ADDR = '224.0.0.10'
MULTICAST_PORT = 49152

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
        self.received_notifs = queue.Queue(10)
        self._configure_cast_sock()

    def _configure_cast_sock(self):
        self.cast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.cast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self.cast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(MULTICAST_ADDR) + socket.inet_aton("0.0.0.0"))
        self.cast_sock.bind(('0.0.0.0', BROADCAST_PORT))

    def cast(self, message):
        self.cast_sock.sendto(message.encode(), (MULTICAST_ADDR, MULTICAST_PORT))
        print('Multicasting:', message)

    def stop_listen(self):
        self.cast_sock.sendto('stop'.encode(), (self.local_ip, MULTICAST_PORT))
        print('Sending signal to stop local listening to multicast')

    def listen_cast(self):
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
                self.received_notifs.put((data, sender_addr, sender_port))


class LocalNode:
    def __init__(self):
        self.local_ip = get_machine_ip()
        self.served_connections = []
        self.client_connections = []

