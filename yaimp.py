#Project: Yet Another Instant Messaging Protocol
#Authors: Jonathan Moore, Michael Sandell, Isaac Rowe
#Class: EE586 Fall 2020
import sys
from socket import *
import time
import json
import select
import concurrent.futures

class Message:
    def __init__(self, src, dest, data, timeout, ACK):
        self.src = src
        self.dest = dest
        self.data = data
        self.timeout = timeout
        self.ACK = ACK

    def print(self):
        print(self.src, self.dest, self.data, self.timeout, self.ACK)

class Host_Node:
    TIMEOUT_DELTA = 60
    LISTEN_PORT = 8080 #The default port to listen on
    BROADCAST_PORT = 9080
    BROADCAST_LIST = [9080, 9081, 9082, 9083, 9084]

    is_writing = False

    received_cache = []
    outbox_cache = []
    peers = []

    #Returns the time that a message should timeout
    def calc_timeout(self):
        return time.time() + self.TIMEOUT_DELTA

    def make_msg(self, dest, src, data, ACK):
        timeout = self.calc_timeout()
        msg = Message(src, dest, data, timeout, ACK)

        return json.dumps(msg.__dict__)

    def update_cache(self, cache):
        current_time = time.time()
        return [msg for msg in cache if msg.timeout < current_time]

    def broadcast_available(self, ACK):
        for b in self.BROADCAST_LIST:
            sock = socket(AF_INET, SOCK_STREAM)
            msg = self.make_msg(b, self.LISTEN_PORT, "", ACK)
            try:
                sock.connect(("", b))
                msg_str = json.dumps(msg)
                sock.sendall(msg_str)
            except:
                print("Error in broadcasting")

        
    # args is a list of messages that should be added into the outbox
    def send_msg(self, *args):
        #Check outbox for timeouts
        self.outbox_cache = self.update_cache(self.outbox_cache)
        # Update the outbox with any messages passed in
        for msg in args:
            out_flag = False
            for m in self.outbox_cache:
                if m is msg:
                    out_flag = True
                if not(out_flag): #if the message is not already in the outbox
                    self.outbox_cache.append(msg)
            print("outbox updated")
            print(self.peers)
        # Send all messages in the outbox to every peer
        for p in self.peers:
            print("Starting to send outbox to ", p)
            sock = socket(AF_INET, SOCK_STREAM)
            try:
                print("trying to connect to ", p)
                sock.connect(("", p))
                print("connected to ", p)
                for message in self.outbox_cache:
                    msg_str = json.dumps(message)
                    print("Sending message \"", msg_str, "\" to ", p)
                    sock.sendall(msg_str)
                    print("Message sent to ", p)
            except Exception as e: 
                print("something's wrong with %d. Exception is %s" % (p, e))
                self.update_peer(p, False)
            sock.close()
            print("Messages sent")

    # Takes in a port number to add or remove from the peer list
    # is_adding should be True to add a peer and False to remove one
    def update_peer(self, peer, is_adding):
        if(peer in self.peers):
            return
        while(self.is_writing):
            pass
        self.is_writing = True
        if(is_adding):
            self.peers.append(peer)
        else:
            self.peers.remove(peer)
        self.is_writing = False

    #Takes in a recieved json string and handles it as needed
    def rcv_msg(self, msg_str):
        print("rcv_msg called")
        #Create a message object from the received message
        msg_dict = json.loads(msg_str)
        message = Message(**msg_dict)
        if(message.dest == self.LISTEN_PORT): #Message is for self
            if message.ACK == True:
                return
            else:
                #Update received cache
                self.received_cache = self.update_cache(self.received_cache)
                rcvd_flag = False
                for m in self.received_cache:
                    if m is message:
                        rcvd_flag = True
                if not(rcvd_flag): #If the message has not been recieved before
                    print("Rcvd message: " + message.data) #deliver message to upper layer
                    self.received_cache.append(message)
                ack_msg = self.make_msg(message.dest, message.src, message.data, True)
                # Send ACK to all peers
                self.send_msg(ack_msg)
        else: #Message is for someone else
            if message.ACK == True: #The message is an ACK for someone else
                if message.src == self.LISTEN_PORT:
                    #deliver confirmation that the message was sent
                    print("Your message \"" + message.data + "\" to " + message.dest + " was delivered")
                    return
                else:
                    if message.timeout < time.time:
                        # forward ACK to all peers
                        self.send_msg(ack_msg)
                        return
            else: #The message is a normal message for somebody else
                # Send message to all peers
                self.send_msg(message)

def get_input(host):
    print("Get_input called by worker thread")
    while True:
        dest_port = input("Type the port you want to send to: ")
        host.update_peer(dest_port, True)
        usr_msg = input("Type your message: ")
        msg = host.make_msg(dest_port, host.LISTEN_PORT, usr_msg, False)
        host.send_msg(msg)

def broadcast_listen(host):
    print("Broadcasting on port ", host.BROADCAST_PORT)
    broadcast_socket = socket(AF_INET, SOCK_STREAM)
    broadcast_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    broadcast_socket.bind(("",host.BROADCAST_PORT))
    broadcast_socket.listen()
    print("Broadcast_listen called by worker")
    while True:
        connect_sock, addr = broadcast_socket.accept() 
        try:
            msg_rcvd = connect_sock.recv(1024)
            msg_dict = json.loads(msg_rcvd)
            message = Message(**msg_dict)
            if(not(message.ACK)):
                host.broadcast_available(True)
                host.update_peer(message.src, True)
            else:
                host.update_peer(message.src, True)
            host.send_msg()
        except:
            print("Error in broadcast_listen")
            pass

def receive_listen(host):
    print("Listening on port ", host.LISTEN_PORT)
    receive_socket = socket(AF_INET, SOCK_STREAM)
    receive_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    receive_socket.bind(("", host.LISTEN_PORT))
    receive_socket.listen()
    print("Receive_listen called by worker")
    while True:
        connect_sock, addr = receive_socket.accept()
        try:
            msg_rcvd = connect_sock.recv(1024)
            host.rcv_msg(msg_rcvd)
        except:
            print("Error in receive_listen")
            pass

# main
def main():
    host = Host_Node()
    if len(sys.argv) > 1:
        listen = sys.argv[1]
        host.LISTEN_PORT = listen
    if len(sys.argv) > 2:
        broad = sys.argv[2]
        host.BROADCAST_PORT = broad
        #host.BROADCAST_LIST.remove(broad)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        message_worker = executor.submit(get_input, host)
        broadcast_worker = executor.submit(broadcast_listen, host)
        receive_worker = executor.submit(receive_listen, host)
                
    # TODO: Set up sockets for listen port and broadcast port
    # TODO: Make sure we accept call on the correct socket (using select?)
    # TODO: Maintain peer list of connected nodes
    # TODO: broadcast hello msg to be added to peer lists
    # TODO: Detect dead peers to remove
# Loop here

if __name__ == "__main__":
    main()