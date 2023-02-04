# Overview

This is a python peer-to-peer networking stack using sockets. It is not recommended for use in end products due to its wide port range it requires to operate.

Start the program by running `network.py`. Each node will scan for peers on the local network and attempt to connect to available peers. User input will be distributed across the network. Peers may recieve redundant messages. **The concurrency via threading on the program is broken, so exiting must be done via keyboard interrupt (Ctrl+C).**

This is an exercise that I've used to learn how socketed connections work over TCP and UDP.

{Provide a link to your YouTube demonstration.  It should be a 4-5 minute demo of the software running (you will need to show two pieces of software running and communicating with each other) and a walkthrough of the code.}

[Software Demo Video](http://youtube.link.goes.here)

# Network Communication

## Handling Peers in Various Scenarios

### No Peers on the Network
When a peer attempts to connect and is the first on the network,
no other peers should be available. In this case, the peer should
exclusively listen for TCP connections and make no attempts to connect to other peers.
The peer should then start using multicast to indicate its availability for connections.

### Peer is Available
When a peer receives a multicast message with the available peers on the network,
including the TCP port that the peer is listening on, it can determine the network load to aid in balancing.
The serving peer then opens a new socket to listen for new connections.
Meanwhile, the connecting peer should also open a new socket and broadcast its availability for connections.

### Peer Shuts Down
If a peer shuts down, whether due to program closure or an error,
the network should be self-healing. All peers with connections to the shutting down peer should reattempt to connect to other peers.
Since each peer should have a fallback connection, this should not totally disconnect peers from the network.

### Nodes Maxed Out Connections
This should not occur unless there are "siphoners" that only connect to other peers without serving new connections.
To prevent this, there should be a 1:1 or many-to-one ratio of incoming to outgoing connections for any given peer.
Peers should also not connect using multiple TCP ports to the same peer.


The program runs the UDP multicast on port 49152 and TCP client and server connections between ports 49152 and 65535.
Make sure to adjust your firewall settings accordingly.

## Format of Message exchange
Messages sent over the network are plain bytestrings representing ascii characters.

# Development Environment

Kate text editor and the CPython interpreter were used for the development environment.
There may be quirks specific to other operating systems (Windows).

The Python programming language is used with the built in `socket` and `threading` libraries, along with other built in modules.

# Useful Websites

Resources

* [`socket` library (Python Docs)](https://docs.python.org/3/library/socket.html#module-socket)
* [Multicasting (Wikipedia)](https://en.wikipedia.org/wiki/Multicast)

# Future Work

* Fix deadlocks in multithreading
* Make peer discovery more efficent
* Make network visualizations using `matplotlib`
