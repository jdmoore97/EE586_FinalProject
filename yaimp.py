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

    is_writing = False

    received_cache = []
    outbox_cache = []
    peers = []

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

    def update_cache(self, cache):
        current_time = time.time()
        #print("Outbox cache in update fn")
        for msg in cache:
            #print(msg.__dict__)
            if msg.timeout < current_time:
                print("Message timed out:", msg.__dict__)
                cache.remove(msg)
        #print([msg.__dict__ for msg in cache if msg.timeout < current_time])
        #return [msg for msg in cache if msg.timeout < current_time]

    #Removes a message from the outbox that an acknowledgment was received for
    #ack_msg is the ACK received for the message that needs to be removed
    def remove_ackd_msg(self, ack_msg):
        for m in self.outbox_cache:
            if(m.src == ack_msg.src and m.dest == ack_msg.dest and m.timeout == ack_msg.timeout):
                print("Removing from outbox: ", m.__dict__)
                self.outbox_cache.remove(m)

    def check_for_ackd_msg(self, msg):
        for m in self.outbox_cache:
            #Returns true if we already have the ACK for the given message
            if(m.src == msg.src and m.dest == msg.dest and m.timeout == msg.timeout and m.ACK != msg.ACK):
                return True
        #Returns false otherwise
        return False

    def broadcast_available(self, ACK):
        print("Broadcasting to:", self.BROADCAST_LIST)
        for b in self.BROADCAST_LIST:
            sock = socket(AF_INET, SOCK_STREAM)
            msg = self.make_msg(b, self.LISTEN_PORT, "", ACK)
            try:
                sock.connect(("", b))
                msg_str = json.dumps(msg.__dict__)
                #print("Message_str:", msg_str)
                #print(b)
                sock.sendall(msg_str.encode())
            except Exception as e:
                print("Error in broadcasting: ", e)

        
    # args is a list of messages that should be added into the outbox
    def send_msg(self, *args):
        #Check outbox for timeouts
        #print("Outbox cache before update:")
        #for outmsg in self.outbox_cache:
        #    print(outmsg.__dict__)
        self.update_cache(self.outbox_cache)
        #print("Outbox cache after update:")
        #for outmsg in self.outbox_cache:
        #    print(outmsg.__dict__)
        # Update the outbox with any messages passed in
        for msg in args:
            out_flag = False
            if not self.outbox_cache:
                out_flag = False
            for m in self.outbox_cache:
                if m.__dict__ == msg.__dict__:
                    out_flag = True
            if not(out_flag): #if the message is not already in the outbox
                self.outbox_cache.append(msg)
                #print("Msg added to outbox")
                for outmsg in self.outbox_cache:
                    print(outmsg.__dict__)
            # print("outbox updated")
            #print("Peers at beginning of send message: ", self.peers)
        #print("Outbox length before checking length:", len(self.outbox_cache))
        if len(self.outbox_cache) == 0:
            print("Nothing in outbox to send")
            return
        # Send all messages in the outbox to every peer
        dead_peers = []
        for p in self.peers:
            if p == self.LISTEN_PORT: #don't send to self
                continue
            print(self.LISTEN_PORT, "starting to send outbox to", p)
            sock = socket(AF_INET, SOCK_STREAM)
            try:
                #print("trying to connect to ", p)
                sock.connect(("", p))
                #print(self.LISTEN_PORT, "connected to ", p)
                #print(self.outbox_cache)
                #print("Outbox length before sending message:", len(self.outbox_cache))
                for message in self.outbox_cache:
                    msg_str = json.dumps(message.__dict__)
                #    print("Sending message \"", msg_str, "\" to ", p)
                    sock.sendall(msg_str.encode())
                 #   print("Message sent to ", p)
                sock.close()
            except Exception as e: 
                print("something's wrong with %d. Exception is %s" % (p, e))
                dead_peers.append(p)
                continue
            #    print("Peer list after update:", self.peers)
        for dead in dead_peers:    
            self.update_peer(dead, False)    
            # print("Messages sent")

    # Takes in a port number to add or remove from the peer list
    # is_adding should be True to add a peer and False to remove one
    def update_peer(self, peer, is_adding):
        print("Update peer called")
        if peer == self.LISTEN_PORT:
            return
        if(is_adding and (peer in self.peers)):
            return
        while(self.is_writing):
            pass
        self.is_writing = True
        if(is_adding):
            self.peers.append(peer)
            print("Added", peer, "to peer list")
        else:
            print("About to remove", peer)
            self.peers.remove(peer)
            print("Peers after removal within update_peers method ", self.peers)
        self.is_writing = False

    #Takes in a received json string and handles it as needed
    def rcv_msg(self, msg_str):
        #print("rcv_msg called")
        #print(msg_str)
        #Create a message object from the received message
        msg_dict = json.loads(msg_str)
        message = Message(**msg_dict)
        #print(type(message.dest))
        #print(message.data)
        if(message.dest == self.LISTEN_PORT): #Message is for self
            if message.ACK == True:
                #remove original message from outbox
                self.remove_ackd_msg(message)
                return
            else:
                print("This was for me!")
                #Update received cache
                self.update_cache(self.received_cache)
                rcvd_flag = False
                for m in self.received_cache:
                    if m.__dict__ == message.__dict__:
                        rcvd_flag = True
                if not(rcvd_flag): #If the message has not been recieved before
                    print("Rcvd message: ", message.data) #deliver message to upper layer
                    self.received_cache.append(message)
                ack_msg = self.make_msg(message.dest, message.src, message.data, True, message.timeout)
                # Send ACK to all peers
                self.send_msg(ack_msg)
        else: #Message is for someone else
            print("This was for someone else!")
            if message.ACK == True: #The message is an ACK for someone else
                #remove original message from outbox
                self.remove_ackd_msg(message)
                if message.src == self.LISTEN_PORT:
                    #deliver confirmation that the message was sent
                    print("Your message \"", message.data , "\" to" , message.dest , "was delivered")
                    self.send_msg(message)
                    return
                else:
                    if message.timeout < time.time():
                        # forward ACK to all peers
                        self.send_msg(message)
                        return
            else: #The message is a normal message for somebody else
                # Send message to all peers if we don't have the ACK for it already
                if(not(self.check_for_ackd_msg(message))):
                    print("Checking for ackd messages")
                    self.send_msg(message)

def get_input(host):
    #print("Get_input called by worker thread")
    while True:
        dest_port = input("Type the port you want to send to: ")
        host.update_peer(int(dest_port), True)
        usr_msg = input("Type your message: ")
        msg = host.make_msg(dest_port, host.LISTEN_PORT, usr_msg, False)
        print(msg)
        print("Calling send_msg from get_input")
        host.send_msg(msg)

def broadcast_listen(host):
    print("Broadcasting on port ", host.BROADCAST_PORT)
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
            print("New peer detected")
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
            print("Received" , len(msg_rcvd), "bytes")
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
    # TODO: Set up sockets for listen port and broadcast port
    # TODO: Make sure we accept call on the correct socket (using select?)
    # TODO: Maintain peer list of connected nodes
    # TODO: broadcast hello msg to be added to peer lists
    # TODO: Detect dead peers to remove
# Loop here

if __name__ == "__main__":
    main()