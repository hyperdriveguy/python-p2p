import json
import socket
import threading
import random
import ipaddress
from time import sleep

def load_game_data(file_path):
    with open(file_path, 'r') as f:
        game_data = json.load(f)
    return game_data

# IP helper function - https://stackoverflow.com/a/28950776
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP



class P2PNode:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcpsock.bind((self.host, self.port))
        self.udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
        self.udpsock.bind(('', self.port))
        while True:
            data, addr = self.udpsock.recvfrom(1024)
            print(f"Received broadcast from {addr}")
            print(data, addr)
            if "game_online" in data.decode():
                self.games_list.append(addr)

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
        except Exception as e:
            print(f"Error: {e}")
            # remove the peer from the games_list
            self.games_list.remove((host, port))
            # try connecting to another peer
            if self.games_list:
                peer = random.choice(self.games_list)
                print(f"Connecting to peer at {peer[0]}:{peer[1]}")
                self.connect(peer[0], peer[1])




    def broadcast(self):
        while True:
            try:
                ip = ipaddress.IPv4Address(socket.gethostbyname(socket.gethostname()))
                print(ip)
                if str(ip) in ('127.0.0.1', '127.0.1.1'):
                    ip = ipaddress.IPv4Address(socket.gethostbyname(socket.gethostname() + '.local'))
                print(ip)
                net = ipaddress.IPv4Network(ip)
                broadcast_ip = str(net.broadcast_address)
                self.udpsock.sendto(f"game_online".encode(), (broadcast_ip, self.port))
                print(f"Broadcasting to {broadcast_ip}:{self.port}")
            except Exception as e:
                print(f"Error: {e}")
            sleep(5) # wait 5 seconds before trying again


if __name__ == '__main__':
    node = P2PNode("0.0.0.0", 1555)
    broadcast_thread = threading.Thread(target=node.broadcast)
    listen_thread = threading.Thread(target=node.udp_listen)
    broadcast_thread.start()
    listen_thread.start()
    while True:
        if node.games_list:
            peer = random.choice(node.games_list)
            print(f"Connecting to peer at {peer[0]}:{peer[1]}")
            node.connect(peer[0], peer[1])
            # break
        sleep(1)

