import json
import socket
import threading
import random
import ipaddress
from time import sleep

MULTICAST_ADDR = '224.0.0.10'
GAME_PORT = 44001

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
        self.host = host
        self.port = port
        self.ip = get_machine_ip()
        self.tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcpsock.bind((self.host, self.port))
        self.udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udpsock.bind(('0.0.0.0', self.port))
        self.games_list = []

    def listen(self):
        self.tcpsock.listen()
        print(f"Listening for incoming connections on {self.host}:{self.port}")
        while True:
            client, addr = self.tcpsock.accept()
            client.send("Welcome to the P2P network!".encode())
            connection_thread = threading.Thread(target=self.handle_connection, args=(client, addr))
            connection_thread.start()

    def udp_listen(self):
        self.udpsock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(MULTICAST_ADDR) + socket.inet_aton("0.0.0.0"))
        while True:
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
        try:
            self.tcpsock.connect((host, port))
            print(f"Connected to {host}:{port}")
            self.tcpsock.send(f"Hello from {self.host}:{self.port}".encode())
            while True:
                data = self.tcpsock.recv(1024).decode()
                if not data:
                    break
                print(f"Received: {data}")
            self.tcpsock.close()
        except OSError as e:
            print(f"Error: {e}")
            # remove the peer from the games_list
            self.games_list.remove((host, port))
            # try connecting to another peer
            if self.games_list:
                peer = random.choice(self.games_list)
                print(f"Connecting to peer at {peer[0]}:{peer[1]}")
                self.connect(peer[0], peer[1])

    def broadcast(self):
        group = (MULTICAST_ADDR, self.port)
        self.udpsock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        while True:
            self.udpsock.sendto("game_online".encode(), group)
            print(f"Broadcasting to {group}")
            sleep(15) # wait 5 seconds before trying again



if __name__ == '__main__':
    node = P2PNode("0.0.0.0", GAME_PORT)
    broadcast_thread = threading.Thread(target=node.broadcast)
    listen_thread = threading.Thread(target=node.udp_listen)
    broadcast_thread.start()
    listen_thread.start()
    while True:
        if node.games_list:
            peer = random.choice(node.games_list)
            print(f"Connecting to peer at {peer[0]}:{GAME_PORT}")
            node.connect(peer[0], GAME_PORT)
            # break
        sleep(1)

