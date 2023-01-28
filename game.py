import json
import socket
import threading
import random
import ipaddress
from time import sleep

MULTICAST_ADDR = '224.0.0.10'
BROADCAST_PORT = 4000
TCP_LISTEN_PORT = BROADCAST_PORT + 1
TCP_CONNECT_PORT = BROADCAST_PORT + 2

def load_game_data(file_path):
    with open(file_path, 'r') as f:
        game_data = json.load(f)
    return game_data

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



class P2PNode:
    def __init__(self, host, port):
        self.stop = False
        self.host = host
        self.port = port
        self.ip = get_machine_ip()
        self.tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcpsock.bind((self.ip, self.port))
        self.udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udpsock.bind(('0.0.0.0', BROADCAST_PORT))
        self.games_list = []


    def listen(self):
        self.tcpsock.listen()
        print(f"Listening for incoming connections on {self.ip}:{TCP_LISTEN_PORT}")
        while not self.stop:
            client, addr = self.tcpsock.accept()
            client.send("Welcome to the P2P network!".encode())
            connection_thread = threading.Thread(target=self.handle_connection, args=(client, addr))
            connection_thread.start()

    def udp_listen(self):
        self.udpsock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(MULTICAST_ADDR) + socket.inet_aton("0.0.0.0"))
        while not self.stop:
            data, sender = self.udpsock.recvfrom(1024)
            sender_addr, sender_port = sender
            if sender_addr != self.ip:
                print(f"Received broadcast from {sender_addr}")
                print(sender_addr, 'reports:', data)
                if "game_online" in data.decode():
                    self.games_list.append(sender_addr)
            else:
                print(f"Ignoring broadcast message from localhost {sender_addr}")

    def connect(self, host, port):
        connect_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # try:
        connect_sock.connect((host, port))
        print(f"Connected to {host}:{port}")
        connect_sock.send(f"Hello from {self.host}:{self.port}".encode())
        while not self.stop:
            data = connect_sock.recv(1024).decode()
            if not data:
                break
            print(f"Received: {data}")
        # except ConnectionRefusedError as e:
        #     print(f"Error: {e}")
        #     # remove the peer from the games_list
        #     self.games_list.remove((host))
        #     # try connecting to another peer
        #     if self.games_list:
        #         peer = random.choice(self.games_list)
        #         print(f"Connecting to peer at {peer[0]}:{peer[1]}")
        #         self.connect(peer, TCP_CONNECT_PORT)
        # finally:
        #     connect_sock.close()


    def broadcast(self):
        group = (MULTICAST_ADDR, BROADCAST_PORT)
        self.udpsock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        while not self.stop:
            self.udpsock.sendto("game_online".encode(), group)
            print(f"Broadcasting to {group}")
            sleep(5) # wait 5 seconds before trying again



if __name__ == '__main__':
    try:
        node = P2PNode("0.0.0.0", BROADCAST_PORT)
        tcp_listen_thread = threading.Thread(target=node.listen)
        broadcast_thread = threading.Thread(target=node.broadcast)
        listen_thread = threading.Thread(target=node.udp_listen)
        tcp_listen_thread.start()
        broadcast_thread.start()
        listen_thread.start()
        while True:
            if node.games_list:
                peer = random.choice(node.games_list)
                print(f"Connecting to peer at {peer}:{TCP_CONNECT_PORT}")
                node.connect(peer, TCP_CONNECT_PORT)
                # break
            sleep(1)
    except KeyboardInterrupt:
        node.stop = True
        print('Stopping local node')
        tcp_listen_thread.join()
        broadcast_thread.join()
        listen_thread.join()

