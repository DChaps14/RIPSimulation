# COSC364 Assignment 1:
# RIP Routing

import sys
import socket
import re
import copy
import select
import random

import time, threading

ROUTING_TABLE = []
SENDING_SOCKET = 0
THIS_ROUTER_ID = 0
NEIGHBOUR_ROUTERS = []
ROUTER_TIMERS = []
REACHABLE_ROUTERS = []
GARBAGE_COLLECTED = []

TIMER_GARBAGE_TIMEOUT = 8
TIMER_SEND_TIMEOUT = 2
TIMER_ROUTE_TIMEOUT = 12



"""Updates this routers routing table, using the routing table sent to us from our peer"""
def update_routing_table(peer_table, peer_id):
    global ROUTING_TABLE
    global REACHABLE_ROUTERS
    peer_port = ""
    peer_cost = ""
    
    #Find the information about the peer who sent us the table
    for i in range(1, len(ROUTING_TABLE)):
        value = ROUTING_TABLE[i]
        if value[0] == str(peer_id):
            peer_port = value[1]
            peer_cost = value[2]
            break

    #Check if the peer is missing from the routing table
    if peer_port == "" or peer_cost == "":
        print("Could not find peer in routing table")
        return

    
    for i in range(len(peer_table)):
        new_router_id = str(peer_table[i][0])
        
        #Ignore the entry if its a connection to this router
        if new_router_id == str(THIS_ROUTER_ID):
            continue
            
        if new_router_id in REACHABLE_ROUTERS:
            #The known_router and routing_table lists will have the same order, and thus the indices will match up
            entry_index = REACHABLE_ROUTERS.index(new_router_id) + 1
            #Find the corresponding routing entry
            routing_entry = ROUTING_TABLE[entry_index]
            
            #Calculate the 2 potential costs
            current_cost = int(routing_entry[2])
            alternate_cost = int(peer_cost) + int(peer_table[i][1])            
            
            #If the same peer has sent us information about a route, update the route information no matter what
            if str(routing_entry[3]) == str(peer_id) and int(routing_entry[2]) < 16:
                routing_entry[2] = str(int(peer_cost) + int(peer_table[i][1]))          
            #If the new incoming cost is better, update the routing table
            elif alternate_cost < current_cost:
                ROUTING_TABLE[entry_index] = [new_router_id, peer_port, str(alternate_cost), peer_id]
                
                
                
            #If the cost is at infinity, call garbage collection
            if int(ROUTING_TABLE[entry_index][2]) >= 16 and current_cost < 16: #this second check is to ensure that we don't repeatedly call the garbage_collection function on a value that may keep getting set above 16
                garbage_collection(ROUTING_TABLE[entry_index][0])            
        else:
            #The new router is not known, add it in the known_routers and routing_table lists
            if int(peer_cost)+int(peer_table[i][1]) < 16:
                REACHABLE_ROUTERS.append(new_router_id)
                new_entry = [new_router_id, peer_port, str(int(peer_cost)+int(peer_table[i][1])), peer_id]
                ROUTING_TABLE.append(new_entry)
 
 
"""Perform error checking on the values passed to us through the router's config file"""
def configErrorCheck(router_id, input_ports, output_ports):
    
    #checks that router_id is valid
    try:
        router_id = int(router_id)
        if router_id < 1 or router_id > 64000:
            sys.exit("ERROR: invalid router id. Please provide an id between 1 and 64000")
    except ValueError:
        sys.exit("ERROR: ensure router id is an integer");
    
    #checks that all input ports are numbers ints and within valid boundry
    try:
        if len(input_ports) != len(set(input_ports)):
            sys.exit("ERROR: ensure no duplicate inport ports");
        for i in input_ports:
            i = int(i)
            if(i < 1024 or i > 64000):
                sys.exit("ERROR: ensure inport ports are valid (between 1024 and 64000)");
    except ValueError:
        sys.exit("ERROR: ensure inport ports are numbers");


    #checks that each output port is in the valid format int-int-int
    #checks each port number to ensure it is within the boundry
    #Checks that the metric is not above the 16 (infinity) threshold
    #lastly checks that the output router_id is also valid
    for i in output_ports:
        x = re.search("[0-9]+-[0-9]+-[0-9]+", i)
        if(x == None):
            sys.exit("ERROR: please ensure that all output_ports are numbers in the correct format 'port_number-link_cost-router_id'\nFor example: 5000-1-2");
        
        i = i.split("-")
        port_number = int(i[0])
        link_cost = int(i[1])
        router_id_output = int(i[2])
        
        if str(port_number) in input_ports:
            sys.exit("Cannot have output ports that are input ports");        
        
        if(port_number < 1024 or port_number > 64000):
            sys.exit("ERROR: invalid output_port port_number: " + str(port_number) + "\nPlease select a port number between 1024 and 64000");
        if router_id_output < 1 or router_id_output > 64000:
            sys.exit("Error: invalid output_port router_id \nMust be between 1 and 64000");
        if link_cost > 16 or link_cost < 1:
            sys.exit("ERROR: Please ensure that link cost is no smaller than 1 and no greater than 15")


"""Gets the name of the config file from the command line, and extracts data from the file
to use with our router"""
def open_config_file():
    config_file = sys.argv[1]
    file = open(config_file)
    lines = file.readlines()
    router_id = None
    input_ports = None
    output_ports = None
    
    for line in lines:
        #Get the router information
        if line.startswith("router"):
            try:
                router_id = int(line.split(':')[1])
            except ValueError:
                sys.exit("ERROR: Ensure router_id is a number...")
        #Get the input-ports information
        elif line.startswith("input-ports"):
            input_ports = line.split(':')[1]
            input_ports = input_ports.strip()
            input_ports = input_ports.split(', ')
        #Get the outputs information
        elif line.startswith("outputs"): 
            output_ports = line.split(':')[1]
            output_ports = output_ports.strip()    
            output_ports = output_ports.split(', ')
    
    if router_id == None:
        sys.exit("ERROR: Please ensure that the router's id is present and marked as 'router-id'")
    elif input_ports == None:
        sys.exit("ERROR: Please ensure that the input ports field is present and marked as 'input-ports'")
    elif output_ports == None:        
        sys.exit("ERROR: Please ensure that the outputs are present and marked as 'outputs'")
    
    return router_id, input_ports, output_ports


"""Create a new timer for the route timeout"""
def timer():    
    #Send packets to all peers
    send_to_routers()
    #Generate a random time for the next timer, which calls this function on expiry
    rand_time = TIMER_SEND_TIMEOUT + random.randint(-5, 5)
    threading.Timer(rand_time, timer).start()
    
"""Resets the route timeout timer for the specified route
Called when we receive a new packet from a neighbouring router"""
def reset_timer(router_id):
    global ROUTER_TIMERS
    
    #Find the timer to reset in ROUTER_TIMERS
    for timer in ROUTER_TIMERS:
        if str(timer[0]) == str(router_id):
            #Remove the Timer from the table and cancel it
            thread = timer[1]
            thread.cancel()
            #Create, start and store a new thread
            new_thread = threading.Timer(TIMER_ROUTE_TIMEOUT, garbage_collection, [router_id])
            new_thread.start()
            timer[1] = new_thread

"""Starts the garbage collection process
Sets a timer, updates the route metric to inifinity (16) in the routing table
Sends this new information to all its neighbouring routers"""
def garbage_collection(router_id):
    global GARBAGE_COLLECTED
    
    #Check that the garbage collection process hasn't started for this entry yet
    if router_id not in GARBAGE_COLLECTED:
        for i in range(1, len(ROUTING_TABLE)):
            if str(ROUTING_TABLE[i][0]) == str(router_id) or str(ROUTING_TABLE[i][3]) == str(router_id):
                ROUTING_TABLE[i][2] = '16'
                GARBAGE_COLLECTED.append([router_id, ROUTING_TABLE[i][0]])

    #Send the updated routing table to all peers
    send_to_routers()
    new_thread = threading.Timer(TIMER_GARBAGE_TIMEOUT, garbage_collection_expiry_check, [router_id])
    new_thread.start()    
    
    
"""Called when a garbage collection timer expires
Checks the routing table: if the garbage entry has ben updated since the timer was started, don't delete it
Otherwise, delete the entry
Router_id: The id of the router that has timed out"""
def garbage_collection_expiry_check(router_id):
    global GARBAGE_COLLECTED
    
    ids_to_remove = []
    routes_to_remove = []
    for route in GARBAGE_COLLECTED:
        #Find each route that routes through the deleted route
        if str(route[0]) == str(router_id):
            ids_to_remove.append(route[1])
            routes_to_remove.append(route)
    
    
    ids_to_remove.sort(reverse=True)
    
    for id_to_remove in ids_to_remove: 
        
        index = None
        
        #Find the index of the entry to delete
        for j in range(1, len(ROUTING_TABLE)):
            if ROUTING_TABLE[j][0] == id_to_remove:
                index = j
                break
            
            
        #Index will be None if the value has already been deleted
        if index != None:
            #If the router is not the one that has timed out, check if it is a neighbour
            if str(id_to_remove) != str(router_id):
                for router in NEIGHBOUR_ROUTERS:
                    if router[0] == id_to_remove:
                        #The router has not gone down, and is a neighbour
                        #Thus reestablish the router in the routing table with its initial cost
                        ROUTING_TABLE[index] = [str(router[0]), str(router[1]), str(router[2]), None]
                        break
            
            if int(ROUTING_TABLE[index][2]) >= 16:
                ROUTING_TABLE.pop(index)
                #Remove the router from neighbour_routers if it is the one that has gone down
                if str(id_to_remove) == str(router_id):
                    for router in NEIGHBOUR_ROUTERS:
                        if router[0] == id_to_remove:
                            NEIGHBOUR_ROUTERS.remove(router)
                            break
                for timer in ROUTER_TIMERS:
                    if timer[0] == id_to_remove:
                        timer[1].cancel()
                        ROUTER_TIMERS.remove(timer)               
                        break
                REACHABLE_ROUTERS.pop(index-1)
            
    for route in routes_to_remove:
        GARBAGE_COLLECTED.remove(route)
        
    
"""Build the packet that will contain our routing table, to be sent to our neighbours
Router-id: The router the packet will be sent to
"""
def buildResponsePacket(router_id):
    rip_response_packet = bytearray()
    command = 2 #request
    version = 2
    
    #Add the header entries
    rip_response_packet += bytearray(command.to_bytes(1, "big"))
    rip_response_packet += bytearray(version.to_bytes(1, "big"))
    rip_response_packet += bytearray(THIS_ROUTER_ID.to_bytes(2, "big"))


    #Get the edited routing table for the specific router
    routing_table_split = getSplitHorizonPoisonTable(router_id)
    for i in range(1, len(routing_table_split)):
        packet_entry = buildRipEntryPacket(routing_table_split[i])
        rip_response_packet += packet_entry

    return rip_response_packet

"""Construct the packet that contains a table entry from our routing table"""
def buildRipEntryPacket(routing_table_entry):
    rip_packet_entry = bytearray()
    must_be_zero = 0
    router_id_from_table = int(routing_table_entry[0])
    metric = int(routing_table_entry[2])
    rip_packet_entry += bytearray(must_be_zero.to_bytes(4, "big"))
    rip_packet_entry += bytearray(router_id_from_table.to_bytes(4, "big"))
    rip_packet_entry += bytearray(must_be_zero.to_bytes(8, "big"))
    rip_packet_entry += bytearray(metric.to_bytes(4, "big"))
    return rip_packet_entry

    
    

"""
Gets a routing table to send to a specified router.
This routing table will be a copy of the router's main routing table, but with
modifications to match split horizon poisoned reverse.

Parameters: router - The router we are sending the table copy to
routing_table - This router's routing table

Returns - A copy of routing_table, with metrics of inf if the next-hop is 'router'
"""
def getSplitHorizonPoisonTable(router):
    #Copy the routing table for each router we are sending to
    #Thus we can change ready = select.select(socket_list, [], [])it without affecting the base router
    routing_table_copy = copy.deepcopy(ROUTING_TABLE)
    for i in range(1, len(routing_table_copy)):
        #If we can reach a dest by routing through the router we are sending to, advertise that route as infinity
        if str(routing_table_copy[i][3]) == router:
            routing_table_copy[i][2] = "16"
    return routing_table_copy

"""Extract the packet header from a received packet and perform some error checks on it"""
def get_header(message):
    #20 is the packet header length
    if len(message) < 20:
        print("Recieved packet is invalid")
        return None
    
    command = int.from_bytes(message[0:1], "big")
    version = int.from_bytes(message[1:2], "big")
    router_id = int.from_bytes(message[2:4], "big")
    
    if version != 2:
        print("invalid version number recieved")
        return None
    if command != 2:
        print("Invalid command number recieved")
        return None

    return router_id

"""Extracts the table sent to us from the peer from the bytearray packet"""
def get_table(message, number):
    peer_table = []
    for i in range(number):
        entry = message[(20*i):(20*(i+1))]
        entry_id = int.from_bytes(entry[4:8], "big")
        entry_metric = int.from_bytes(entry[16:20], "big")
        table_entry = [entry_id, entry_metric]
        peer_table.append(table_entry)
    return peer_table
    
"""Extracts the packet from the socket, and gets the message and its information from the packet"""
def unpack_packet(router_socket):
    router_response = router_socket.recv(512)
    total_bytes = len(router_response)
    message = bytearray(total_bytes)
    message[0:total_bytes] = router_response
    
    #Check if there is a suitable amount of bytes to house an integer amount of packets
    if ((len(message)-4)%20) != 0:
        print("Invalid number of packets recieved")
        del message, router_response
        return None
    
    number_of_packets = (len(message)-4)//20
    router_recvd_from = get_header(message)
    
    #An error occured in get_header, return None
    if router_recvd_from == None:
        del message, router_response
        return None
    peer_table = get_table(message[4:len(message)], number_of_packets)
    return [peer_table, router_recvd_from]
    
"""Send a unique packet containing our routing table to each of our neighbours"""
def send_to_routers():
    #Router contains [router_id, port number]
    for router in NEIGHBOUR_ROUTERS:
        packet = buildResponsePacket(router[0])
        send(router[1], packet)
        #Send across each socket

"""Sends a bytearray packet to the specified destination port through the specified socket"""
def send(dest_port, packet):
    try:
        SENDING_SOCKET.sendto(packet, ("127.0.0.1", int(dest_port)))
    except:
        print("Could not send on socket:")
        print(socket)
        
    
"""If a neighbour router goes down, and is reestablished again, extract the link cost
for the connection to the neighbour from the initial config file"""
def reestablish_router(router_id):
    global ROUTING_TABLE
    global REACHABLE_ROUTERS
    global NEIGHBOUR_ROUTERS
    global ROUTER_TIMERS
    
    ignore, also_ignore, output_ports = open_config_file();
    for i in range(len(output_ports)):
        output_details = output_ports[i].split('-')
        if output_details[2] == str(router_id):
            ROUTING_TABLE.append([output_details[2], output_details[0].strip(), output_details[1], None])
            REACHABLE_ROUTERS.append(output_details[2]) #store the id
            NEIGHBOUR_ROUTERS.append([output_details[2], output_details[0], output_details[1]])
            thread = threading.Timer(TIMER_ROUTE_TIMEOUT, garbage_collection, [output_details[2]])
            ROUTER_TIMERS.append([output_details[2], thread])

"""Prints each route in the routing table in a nice format"""
def print_routing_table():
    print("Routing table for " + str(THIS_ROUTER_ID))
    for route in ROUTING_TABLE:
        print(route)

def main():
    global ROUTING_TABLE
    global SENDING_SOCKET
    global THIS_ROUTER_ID
    global NEIGHBOUR_ROUTERS
    global ROUTER_TIMERS
    global REACHABLE_ROUTERS
    
    router_id, input_ports, output_ports = open_config_file();

    
    #calls configFileErrorCheck, will sys.exit if any part of the file is wrong    
    configErrorCheck(router_id, input_ports, output_ports)    
    
    socket_list = []

    #Create a new socket for each input port provided, and add them to the list of sockets
    for i in range(len(input_ports)):
        new_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        new_socket.bind(("127.0.0.1",int(input_ports[i])))
        socket_list.append(new_socket)
    
    routing_table = [[]]*(len(output_ports)+1)
    reachable_routers = []
    neighbour_routers = []
    router_timers = []
    routing_table[0] = ["Router ID", "Port Number", "Link Cost", "Neighbour Learned From"]
    for i in range(len(output_ports)):
        output_details = output_ports[i].split('-')

        reachable_routers.append(output_details[2]) #store the id
        neighbour_routers.append([output_details[2], output_details[0], output_details[1]])
        routing_table[i+1] = [output_details[2], output_details[0], output_details[1], None]
        thread = threading.Timer(TIMER_ROUTE_TIMEOUT, garbage_collection, [output_details[2]])
        router_timers.append([output_details[2], thread])
    
    
    
    ROUTING_TABLE = routing_table
    
    SENDING_SOCKET = socket_list[0]
    
    THIS_ROUTER_ID = router_id
    
    NEIGHBOUR_ROUTERS = neighbour_routers
    
    ROUTER_TIMERS = router_timers
    REACHABLE_ROUTERS = reachable_routers
    
    for entry in ROUTER_TIMERS:
        entry[1].start()
    
    timer()
    
    while True:
        try:
            ready = select.select(socket_list, [], [])
            ready_socket = ready[0][0]
            peer_info = unpack_packet(ready_socket)
            
            if peer_info == None:
                #An error occured, continue waiting
                continue
            
            
            #Check if the peer has been removed from the routing table previously
            found = False
            for i in range(len(routing_table)):
                if routing_table[i][0] == str(peer_info[1]):
                    found = True
                    break;
            #If the neighbour has been removed, reestablish the neighbour 
            if not found:
                reestablish_router(peer_info[1])                
            else:    
                reset_timer(peer_info[1])
                
            update_routing_table(peer_info[0], peer_info[1])
            print_routing_table()
        except Exception as e:
            print(e)
            continue

        

if __name__ == "__main__":
    main()