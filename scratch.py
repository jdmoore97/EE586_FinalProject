#Project: Yet Another Instant Messaging Protocol
#Authors: Jonathan Moore, Michael Sandell, Isaac Rowe
#Class: EE586 Fall 2020
import sys
from socket import *
import time
import json
import select
import concurrent.futures
import threading

class Message:
    def __init__(self, src, dest, data, timeout, ACK):
        self.src = int(src)
        self.dest = int(dest)
        self.data = data
        self.timeout = float(timeout)
        self.ACK = ACK

    def print(self):
        print(self.src, self.dest, self.data, self.timeout, self.ACK)

class Host_Node:
    TIMEOUT_DELTA = 60
    LISTEN_PORT = 8080 #The default port to listen on
    BROADCAST_PORT = 9080
    BROADCAST_LIST = [9080, 9081, 9082, 9083, 9084]

    is_writing_peer = False
    #is_writing_cache = False    

    received_cache = []
    outbox_cache = []
    peers = []
    outbox_lock = threading.Lock()
    received_lock = threading.Lock()

    #Returns the time that a message should timeout
    def calc_timeout(self):
        return time.time() + self.TIMEOUT_DELTA

    #The last argument is an optional timeout value. If no timeout is passed in, a new one is calculated.
    def make_msg(self, dest, src, data, ACK, *args):
        if(len(args) > 0):
            t_out = float(args[0])
        else:
            t_out = self.calc_timeout()
        msg = Message(src, dest, data, t_out, ACK)
        return msg

    def remove_timeouts(self, cache):
        current_time = time.time()
        for msg in cache:
            if msg.timeout < current_time:
                print("Message timed out:", msg.__dict__)
                self.update_cache(cache, msg, False)

    def update_cache(self, cache, message, is_adding):
        print("waiting for cache to become available to add/remove")
        if cache is self.outbox_cache:
            lock = self.outbox_lock
        else:
            lock = self.received_lock
        with lock:
            print("Taking cache")
            if(is_adding):
                print("adding message to cache:", message.__dict__)
                for m in cache:
                    # No need if the message is already in here
                    if m.__dict__ == message.__dict__:
                        print("Message was already in cache")
                        return
                    # If incoming message is an ACK and the original message is in here, remove it
                    if m.src == message.src and m.dest == message.dest and m.data == message.data and m.timeout == message.timeout:
                        if message.ACK:
                            print("Removing original message corresponding to this ACK")
                            cache.remove(m)
                        else:
                            print("Ignoring because we already have an ACK for this message")                           
                            return
                cache.append(message)
            else:
                print("Removing message from cache", message.__dict__)
                cache.remove(message)
            print("Releasing cache")

    # Takes in a port number to add or remove from the peer list
    # is_adding should be True to add a peer and False to remove one
    def update_peer(self, peer, is_adding):
        if peer == self.LISTEN_PORT:
            return
        if(is_adding and (peer in self.peers)):
            return
        while(self.is_writing_peer):
            pass
        self.is_writing_peer = True
        if(is_adding):
            self.peers.append(peer)
            print("Added", peer, "to peer list")
        else:
            print("Removing", peer, "from peer list")
            self.peers.remove(peer)
        self.is_writing_peer = False

    def broadcast_available(self, ACK):
        for b in self.BROADCAST_LIST:
            sock = socket(AF_INET, SOCK_STREAM)
            msg = self.make_msg(b, self.LISTEN_PORT, "", ACK)
            try:
                sock.connect(("", b))
                msg_str = json.dumps(msg.__dict__)
                sock.sendall(msg_str.encode())
            except Exception as e:
                #print("Error in broadcasting: ", e)
                pass

        
    # args is a list of messages that should be added into the outbox
    def send_msg(self, *args):
        #Check outbox for timeouts
        self.remove_timeouts(self.outbox_cache)
        # Update the outbox with any messages passed in
        for msg in args:
            self.update_cache(self.outbox_cache, msg, True)
        if len(self.outbox_cache) == 0:
            return
        # Send all messages in the outbox to every peer
        dead_peers = []
        for p in self.peers:
            with self.outbox_lock:
                for message in self.outbox_cache:
                    if p == self.LISTEN_PORT: #don't send to self
                        continue
                    sock = socket(AF_INET, SOCK_STREAM)
                    try:
                        sock.connect(("", p))
                        msg_str = json.dumps(message.__dict__)
                        if(message.ACK):
                            print("Sending ACK to ", p,":")
                        else:
                            print("Sending message to ", p,":")
                        sock.sendall(msg_str.encode())
                        sock.close()
                    except Exception as e: 
                        print("something's wrong with %d. Exception is %s" % (p, e))
                        dead_peers.append(p)
                        continue
        for dead in dead_peers:    
            self.update_peer(dead, False)    

    #Takes in a received json string and handles it as needed
    def rcv_msg(self, msg_str):
        #Create a message object from the received message
        msg_dict = json.loads(msg_str)
        message = Message(**msg_dict)
        self.remove_timeouts(self.received_cache)
        # If we got this message before, do nothing 
        with self.received_lock:
            for m in self.received_cache: 
                if m.__dict__ == message.__dict__:
                    return
        self.update_cache(self.received_cache, message, True)
        if message.ACK:
            # The message is an acknowledgement
            # Check to see if we were the original sender.
            with self.outbox_lock:
                match = None
                for m in self.outbox_cache:
                    if message.src == self.LISTEN_PORT and message.dest == m.dest and message.data == m.data and message.timeout == m.timeout:
                        match = message
                        break
            if match is not None:
                # We were the original sender
                self.update_cache(self.outbox_cache, match, True)
                #deliver confirmation that the message was sent
                print("Your message \"", message.data , "\" to" , message.dest , "was delivered")
                return
        else: # Check if we were the intended receiver or if we need to pass it on
            if message.dest == self.LISTEN_PORT:
                # We were the intended receiver
                print("It's for us")
                print("Rcvd message from", message.src, ": ", message.data) #deliver message to upper layer
                ack_msg = self.make_msg(message.dest, message.src, message.data, True, message.timeout)
                # Send ACK to all peers
                self.send_msg(ack_msg)
            else:
                # Not for us, pass it on
                self.send_msg(message)

def get_input(host):
    #print("Get_input called by worker thread")
    while True:
        dest_port = input("Type the port you want to send to: ")
        host.update_peer(int(dest_port), True)
        usr_msg = input("Type your message: ")
        msg = host.make_msg(dest_port, host.LISTEN_PORT, usr_msg, False)
        print("Calling send_msg from get_input")
        host.send_msg(msg)

def broadcast_listen(host):
    #print("Broadcasting on port ", host.BROADCAST_PORT)
    broadcast_socket = socket(AF_INET, SOCK_STREAM)
#    print("Broadcast socket created")
    broadcast_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
#    print("Broadcast options set")
    broadcast_socket.bind(("",host.BROADCAST_PORT))
#    print("Broadcast socket bound to ", host.BROADCAST_PORT)
    broadcast_socket.listen()
#    print("Broadcast_listen called by worker")
    while True:
        connect_sock, addr = broadcast_socket.accept() 
        try:
            #print("New peer detected")
            msg_rcvd = connect_sock.recv(1024).decode()
            msg_dict = json.loads(msg_rcvd)
            message = Message(**msg_dict)
            print("Detected peer at", message.src)
            if(not(message.ACK)):
                host.broadcast_available(True)
                host.update_peer(message.src, True)
            else:
                host.update_peer(message.src, True)
            print("Calling send_msg from broadcast_listen")
            host.send_msg()
        except Exception as e:
            print("Error in broadcast_listen")
            print(e)
            pass

def receive_listen(host):
    print("Listening on port ", host.LISTEN_PORT)
    receive_socket = socket(AF_INET, SOCK_STREAM)
  #  print("Listen socket created")
    receive_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
  #  print("Listen socket options set")
    receive_socket.bind(("", host.LISTEN_PORT))
  #  print("Listen socket bound to ", host.LISTEN_PORT)
    receive_socket.listen()
   # print("Receive_listen called by worker")
    while True:
        connect_sock, addr = receive_socket.accept()
        try:
            msg_rcvd = connect_sock.recv(1024).decode()
            #print("Received" , len(msg_rcvd), "bytes")
            host.rcv_msg(msg_rcvd)
        except Exception as e: 
            print("Exception is %s" % e)
            print("Error in receive_listen")
            pass

# main
def main():
    host = Host_Node()
    if len(sys.argv) > 1:
        listen = sys.argv[1]
        host.LISTEN_PORT = int(listen)
    if len(sys.argv) > 2:
        broad = sys.argv[2]
        host.BROADCAST_PORT = int(broad)
    host.BROADCAST_LIST.remove(host.BROADCAST_PORT)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        message_worker = executor.submit(get_input, host)
        broadcast_worker = executor.submit(broadcast_listen, host)
        receive_worker = executor.submit(receive_listen, host)
        host.broadcast_available(False)

if __name__ == "__main__":
    main()