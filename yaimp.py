#Project: Yet Another Instant Messaging Protocol
#Authors: Jonathan Moore, Michael Sandell, Isaac Rowe
#Class: EE586 Fall 2020
import sys
import socket
import time
import json

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

    received_cache = []
    outbox_cache = []

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
        
    def send_msg():

    #Takes in a recieved json string and handles it as needed
    def rcv_msg(self, msg_str):
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
                # TODO: Send ACK to all peers
        else: #Message is for someone else
            if message.ACK == True:
                if message.src == self.LISTEN_PORT:
                    #deliver confirmation that the message was sent
                    print("Your message \"" + message.data + "\" to " + message.dest + " was delivered")
                    return
                else:
                    if message.timeout < time.time:
                        # TODO: forward ACK to all peers
                        return
            else:
                self.outbox_cache = self.update_cache(self.outbox_cache)
                out_flag = False
                for m in self.outbox_cache:
                    if m is message:
                        out_flag = True
                if not(out_flag): #if the message is not already in the outbox
                    self.outbox_cache.append(message)

# main
if __name__ == "__main__":
    if len(sys.argv) > 1:
        LISTEN_PORT = sys.argv[1]
    host = Host_Node()
    m = host.make_msg(8081, 8080, "This is a test", False)
    print(m)
    msg_dict = json.loads(m)
    message = Message(**msg_dict)
    message.print()

    # TODO: Set up sockets for listen port and broadcast port
    # TODO: Make sure we accept call on the correct socket (using select?)
    # TODO: Maintain peer list of connected nodes
    # TODO: broadcast hello msg to be added to peer lists
    # TODO: Detect dead peers to remove
# Loop here