# Handling Peers in Various Scenarios

## No Peers on the Network
When a peer attempts to connect and is the first on the network,
no other peers should be available. In this case, the peer should
exclusively listen for TCP connections and make no attempts to connect to other peers.
The peer should then start using multicast to indicate its availability for connections.

## Peer is Available
When a peer receives a multicast message with the available peers on the network,
including the TCP port that the peer is listening on, it can determine the network load to aid in balancing.
The serving peer then opens a new socket to listen for new connections.
Meanwhile, the connecting peer should also open a new socket and broadcast its availability for connections.

## Peer Shuts Down
If a peer shuts down, whether due to program closure or an error,
the network should be self-healing. All peers with connections to the shutting down peer should reattempt to connect to other peers.
Since each peer should have a fallback connection, this should not totally disconnect peers from the network.

## Nodes Maxed Out Connections
This should not occur unless there are "siphoners" that only connect to other peers without serving new connections.
To prevent this, there should be a 1:1 or many-to-one ratio of incoming to outgoing connections for any given peer.
Peers should also not connect using multiple TCP ports to the same peer.
