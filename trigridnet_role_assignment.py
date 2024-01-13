# This simulation tests a distributed role assignment algorithm, for robot swarm starting
# at arbitrary triangle grid network, to perform one-to-one role assignment. The assigned
# roles are abstract and represented as index numbers. The primary goal of this role
# assignment algorithm is to have all nodes agree on the one-to-one assignment scheme,
# instead of coming up with the best assignment scheme.

# input arguments:
# '-f': filename of the triangle grid network

# Inter-node communication is used to let one node know the status of another node that
# is not directly connected. Enabling message relay is what I consider the most convenient
# way to resolve conflict when two nodes decide on the same assigned role. Although in this
# way, it is possible for each node to have the information of all the other nodes, and
# thus it could become a distributed master control algorithm, we still consider the proposed
# algorithm a distributed one. Because we limit the information each node will store, and
# the local computation performed, so the algorithm is still robust.

# The communication delay is also reflected in the simulation, one step in simulation will
# update one step of message transmission. Color is used to highlight the conflicts in the
# role assignment, instead of showing convergence of decisions.

# visualization design:
# solid black circle for undetermined role assignment scheme
# solid colored circle for conflicts in role assignment
# extra circle on node for locally converged role assignment scheme


import pygame
import matplotlib.pyplot as plt
from trigridnet_generator import *
from formation_functions import *
import numpy as np
import os, getopt, sys, time, random

import pandas as pd
pd.set_option('display.max_columns', None)
# print pd.DataFrame(gradients, range(net_size), range(net_size))

net_folder = 'trigrid-networks'
net_filename = '30-1'  # default network
net_size = 30  # default network size
net_filepath = os.path.join(os.getcwd(), net_folder, net_filename)

# read command line options
try:
    opts, args = getopt.getopt(sys.argv[1:], 'f:')
except getopt.GetoptError as err:
    print(str(err))
    sys.exit()
for opt,arg in opts:
    if opt == '-f':
        net_filename = arg
        net_filepath = os.path.join(os.getcwd(), net_folder, net_filename)
        # check if this file exists
        if not os.path.isfile(net_filepath):
            print("{} does not exist".format(net_filename))
            sys.exit()
        # parse the network size
        net_size = int(net_filename.split('-')[0])

# read the network from file
nodes_tri = []
# nodes_tri: node positions in the triangle grid network
# nodes_cart: node positions in Cartesian coordinates
# nodes_disp: node positions for display
f = open(net_filepath, 'r')
new_line = f.readline()
while len(new_line) != 0:
    pos_str = new_line[0:-1].split(' ')
    pos = [int(pos_str[0]), int(pos_str[1])]
    nodes_tri.append(pos)
    new_line = f.readline()

# generate the connection matrix, 0 for not connected, 1 for connected
connections = np.zeros((net_size, net_size))
for i in range(net_size):
    for j in range(i+1, net_size):
        diff_x = nodes_tri[i][0] - nodes_tri[j][0]
        diff_y = nodes_tri[i][1] - nodes_tri[j][1]
        if abs(diff_x) + abs(diff_y) == 1 or diff_x * diff_y == -1:
            connections[i,j] = 1
            connections[j,i] = 1
# connection list indexed by node
connection_lists = []
for i in range(net_size):
    connection_lists.append(list(np.where(connections[i] == 1)[0]))

# plot the network as dots and lines in pygame window
pygame.init()
font = pygame.font.SysFont("Cabin", 14)
nodes_cart = np.array([trigrid_to_cartesian(pos) for pos in nodes_tri])
# find appropriate window size to fit current network
(xmin, ymin) = np.amin(nodes_cart, axis=0)
(xmax, ymax) = np.amax(nodes_cart, axis=0)
clearance = 2.0
world_size = (xmax-xmin + clearance, ymax-ymin + clearance)
pixels_per_length = 50  # corresponds to 1.0 length in cartesian world
screen_size = (int(round(world_size[0] * pixels_per_length)),
               int(round(world_size[1] * pixels_per_length)))
node_size = 8
line_width = 4
converge_ring_size = 12
# colors
color_white = (255,255,255)
color_black = (0,0,0)
distinct_color_set = ((230,25,75), (60,180,75), (255,225,25), (0,130,200), (245,130,48),
    (145,30,180), (70,240,240), (240,50,230), (210,245,60), (250,190,190),
    (0,128,128), (230,190,255), (170,110,40), (255,250,200), (128,0,0),
    (170,255,195), (128,128,0), (255,215,180), (0,0,128), (128,128,128))
color_quantity = len(distinct_color_set)
# simulation window
icon = pygame.image.load("icon_geometry_art.jpg")
pygame.display.set_icon(icon)
screen = pygame.display.set_mode(screen_size)
pygame.display.set_caption("Role Assignment on 2D Triangle Grid Network")

# node display positions
center_temp = (nodes_cart.max(axis=0) + nodes_cart.min(axis=0))/2.0
nodes_cart = nodes_cart - center_temp + (world_size[0]/2.0, world_size[1]/2.0)
nodes_disp = [world_to_display(nodes_cart[i], world_size, screen_size)
              for i in range(net_size)]

# draw the network for the first time
screen.fill(color_white)
for i in range(net_size):
    for j in range(i+1, net_size):
        if connections[i,j]:
            pygame.draw.line(screen, color_black, nodes_disp[i], nodes_disp[j], line_width)
for i in range(net_size):
    pygame.draw.circle(screen, color_black, nodes_disp[i], node_size, 0)
    # text = font.render(str(i), True, color_black)
    # screen.blit(text, (nodes_disp[i][0]+12, nodes_disp[i][1]-12))
pygame.display.update()

input("press <ENTER> to continue")

########## the role assignment algorithm ##########

# Gradient value method for information flow control:
# This gradient method was first used in the early simulations of Kilobot project, for a robot
# to localize itself in a swarm in order to do formation control. The gradient value indicates
# the distance from a particular source, and can be used here to guarantee the information
# flows only forward, instead of backward. If the source node has gradient value of 0, all the
# nodes next to it will have gradient value of 1, then nodes next to them have gradient value
# of 2. These nodes are forming nested-ring patterns. The message will only be transmitted from
# a low gradient node to a high gradient one. In this way, one message from source will travel
# through all other nodes, without resonating infinitely inside the network. Since every node
# in this application will transmit its own message, the node needs to calculate the gradient
# value of all message sources.

# To construct the gradient values in a distributed way, when messages are received from a new
# message source, the node will take the minimum gradient value plus 1 as its gradient for
# that message source. In this way each node will build the gradient values on-the-go for any
# other message source. A little more complicated algorithm for constructing gradient values
# is also developed to deal with any unstable communication for message transmissions.

# However, to simplify the role assignment simulation, the gradient map is pre-calculated.
# Although I could use algorithm similar in the holistic dependency calculation, a new one that
# searching the shortest path between any two nodes is investigated in the following.
gradients = np.copy(connections)  # build gradient map on the connection map
    # gradients[i,j] indicates gradient value of node j, to message source i
pool_gradient = 1  # gradients of the connections in the pool
pool_conn = {}
for i in range(net_size):
    pool_conn[i] = connection_lists[i][:]  # start with gradient 1 connections
while len(pool_conn.keys()) != 0:
    source_deactivate = []
    for source in pool_conn:
        targets_temp = []  # the new targets
        for target in pool_conn[source]:
            for target_new in connection_lists[target]:
                if target_new == source: continue  # skip itself
                if gradients[source, target_new] == 0:
                    gradients[source, target_new] = pool_gradient + 1
                    targets_temp.append(target_new)
        if len(targets_temp) == 0:
            source_deactivate.append(source)
        else:
            pool_conn[source] = targets_temp[:]  # update with new targets
    for source in source_deactivate:
        pool_conn.pop(source)  # remove the finished sources
    pool_gradient = pool_gradient + 1

# calculate the relative gradient values
gradients_rel = []
    # gradients_rel[i][j,k] refers to gradient of k relative to j with message source i
for i in range(net_size):  # message source i
    gradient_temp = np.zeros((net_size, net_size))
    for j in range(net_size):  # in the view point of j
        gradient_temp[j] = gradients[i] - gradients[i,j]
    gradients_rel.append(gradient_temp)

# list the neighbors a node can send message to regarding a message source
neighbors_send = [[[] for j in range(net_size)] for i in range(net_size)]
    # neighbors_send[i][j][k] means, if message from source i is received in j,
    # it should be send to k
for i in range(net_size):  # message source i
    for j in range(net_size):  # in the view point of j
        for neighbor in connection_lists[j]:
            if gradients_rel[i][j,neighbor] == 1:
                neighbors_send[i][j].append(neighbor)

# generate the initial preference distribution
pref_dist = np.random.rand(net_size, net_size)  # no need to normalize it
initial_roles = np.argmax(pref_dist, axis=1)  # the chosen role

# the local assignment information
local_role_assignment = [[[-1, 0, -1] for j in range(net_size)] for i in range(net_size)]
    # local_role_assignment[i][j] is local assignment information of node i for node j
    # first number is chosen role, second is probability, third is time stamp
local_node_assignment = [[[] for j in range(net_size)] for i in range(net_size)]
    # local_node_assignment[i][j] is local assignment of node i for role j
    # contains a list of nodes that choose role j
# populate the chosen role of itself to the local assignment information
for i in range(net_size):
    local_role_assignment[i][i][0] = initial_roles[i]
    local_role_assignment[i][i][1] = pref_dist[i, initial_roles[i]]
    local_role_assignment[i][i][2] = 0
    local_node_assignment[i][initial_roles[i]].append(i)

# received message container for all nodes
message_rx = [[] for i in range(net_size)]
# for each message entry, it containts:
    # message[0]: ID of message source
    # message[1]: its preferred role
    # message[2]: probability of chosen role
    # message[3]: time stamp
# all nodes transmit once their chosen role before the loop
transmission_total = 0  # count message transmissions for each iteration
iter_count = 0  # also used as time stamp in message
for source in range(net_size):
    chosen_role = local_role_assignment[source][source][0]
    message_temp = [source, chosen_role, pref_dist[source, chosen_role], iter_count]
    for target in connection_lists[source]:  # send to all neighbors
        message_rx[target].append(message_temp)
        transmission_total = transmission_total + 1
role_color = [0 for i in range(net_size)]  # colors for a conflicting role
# Dynamically manage color for conflicting nodes is unnecessarily complicated, might as
# well assign the colors in advance.
role_index_pool = list(range(net_size))
random.shuffle(role_index_pool)
color_index_pool = list(range(color_quantity))
random.shuffle(color_index_pool)
while len(role_index_pool) != 0:
    role_color[role_index_pool[0]] = color_index_pool[0]
    role_index_pool.pop(0)
    color_index_pool.pop(0)
    if len(color_index_pool) == 0:
        color_index_pool = list(range(color_quantity))
        random.shuffle(color_index_pool)

# flags
transmit_flag = [[False for j in range(net_size)] for i in range(net_size)]
    # whether node i should transmit received message of node j
change_flag = [False for i in range(net_size)]
    # whether node i should change its chosen role
scheme_converged = [False for i in range(net_size)]

sim_exit = False
sim_pause = False
time_now = pygame.time.get_ticks()
time_last = time_now
time_period = 2000
speed_control = True  # set False to skip speed control
flash_delay = 200
while not sim_exit:
    # exit the program by close window button, or Esc or Q on keyboard
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            sim_exit = True  # exit with the close window button
        if event.type == pygame.KEYUP:
            if event.key == pygame.K_SPACE:
                sim_pause = not sim_pause  # reverse the pause flag
            if (event.key == pygame.K_ESCAPE) or (event.key == pygame.K_q):
                sim_exit = True  # exit with ESC key or Q key

    # skip the rest if paused
    if sim_pause: continue

    # simulation speed control
    time_now = pygame.time.get_ticks()
    if (time_now - time_last) > time_period:
        time_last = time_now
    else:
        continue

    iter_count = iter_count + 1

    # process the received messages
    # transfer messages to the processing buffer, then empty the message receiver
    message_rx_buf = [[[k for k in j] for j in i] for i in message_rx]
    message_rx = [[] for i in range(net_size)]
    yield_nodes = []  # the nodes that are yielding on chosen roles
    yield_roles = []  # the old roles of yield_nodes before yielding
    for i in range(net_size):  # messages received by node i
        for message in message_rx_buf[i]:
            source = message[0]
            role = message[1]
            probability = message[2]
            time_stamp = message[3]
            if source == i:
                print("error, node {} receives message of itself".format(i))
                sys.exit()
            if time_stamp > local_role_assignment[i][source][2]:
                # received message will only take any effect if time stamp is new
                # update local_node_assignment
                role_old = local_role_assignment[i][source][0]
                if role_old >= 0:  # has been initialized before, not -1
                    local_node_assignment[i][role_old].remove(source)
                local_node_assignment[i][role].append(source)
                # update local_role_assignment
                local_role_assignment[i][source][0] = role
                local_role_assignment[i][source][1] = probability
                local_role_assignment[i][source][2] = time_stamp
                transmit_flag[i][source] = True
                # check conflict with itself
                if role == local_role_assignment[i][i][0]:
                    if probability >= pref_dist[i, local_role_assignment[i][i][0]]:
                        # change its choice after all message received
                        change_flag[i] = True
                        yield_nodes.append(i)
                        yield_roles.append(local_role_assignment[i][i][0])
    # change the choice of role for those decide to
    for i in range(net_size):
        if change_flag[i]:
            change_flag[i] = False
            role_old = local_role_assignment[i][i][0]
            pref_dist_temp = np.copy(pref_dist[i])
            pref_dist_temp[local_role_assignment[i][i][0]] = -1
                # set to negative to avoid being chosen
            for j in range(net_size):
                if len(local_node_assignment[i][j]) != 0:
                    # eliminate those choices that have been taken
                    pref_dist_temp[j] = -1
            role_new = np.argmax(pref_dist_temp)
            if pref_dist_temp[role_new] < 0:
                print("error, node {} has no available role".format(i))
                sys.exit()
            # role_new is good to go
            # update local_node_assignment
            local_node_assignment[i][role_old].remove(i)
            local_node_assignment[i][role_new].append(i)
            # update local_role_assignment
            local_role_assignment[i][i][0] = role_new
            local_role_assignment[i][i][1] = pref_dist[i][role_new]
            local_role_assignment[i][i][2] = iter_count
            transmit_flag[i][i] = True
    # transmit the received messages or initial new message transmission
    transmission_total = 0
    for transmitter in range(net_size):  # transmitter node
        for source in range(net_size):  # message is for this source node
            if transmit_flag[transmitter][source]:
                transmit_flag[transmitter][source] = False
                message_temp = [source, local_role_assignment[transmitter][source][0],
                                        local_role_assignment[transmitter][source][1],
                                        local_role_assignment[transmitter][source][2]]
                for target in neighbors_send[source][transmitter]:
                    message_rx[target].append(message_temp)
                    transmission_total = transmission_total + 1

    # check if role assignment scheme is converged at individual node
    for i in range(net_size):
        if not scheme_converged[i]:
            converged = True
            for j in range(net_size):
                if len(local_node_assignment[i][j]) != 1:
                    converged  = False
                    break
            if converged:
                scheme_converged[i] = True

    # for display, scan the nodes that have detected conflict but not yielding
    persist_nodes = []
    for i in range(net_size):
        if i in yield_nodes: continue
        if len(local_node_assignment[i][local_role_assignment[i][i][0]]) > 1:
            persist_nodes.append(i)

    # debug print
    print("iteration {}, total transmission {}".format(iter_count, transmission_total))

    # update the display
    for i in range(net_size):
        for j in range(i+1, net_size):
            if connections[i,j]:
                pygame.draw.line(screen, color_black, nodes_disp[i], nodes_disp[j], line_width)
    for i in range(net_size):
        pygame.draw.circle(screen, color_black, nodes_disp[i], node_size, 0)
    # draw the persisting nodes with color of conflicting role
    for i in persist_nodes:
        pygame.draw.circle(screen, distinct_color_set[role_color[local_role_assignment[i][i][0]]],
            nodes_disp[i], node_size, 0)
    # draw extra ring on node if local scheme has converged
    for i in range(net_size):
        if scheme_converged[i]:
            pygame.draw.circle(screen, color_black, nodes_disp[i], converge_ring_size, 2)
    pygame.display.update()
    # flash the yielding nodes with color of old role
    for _ in range(3):
        # change to color
        for i in range(len(yield_nodes)):
            pygame.draw.circle(screen, distinct_color_set[role_color[yield_roles[i]]],
                nodes_disp[yield_nodes[i]], node_size, 0)
        pygame.display.update()
        pygame.time.delay(flash_delay)
        # change to black
        for i in range(len(yield_nodes)):
            pygame.draw.circle(screen, color_black,
                nodes_disp[yield_nodes[i]], node_size, 0)
        pygame.display.update()
        pygame.time.delay(flash_delay)

    # exit the simulation if all role assignment schemes have converged
    all_converged = scheme_converged[0]
    for i in range(1, net_size):
        all_converged = all_converged and scheme_converged[i]
        if not all_converged: break
    if all_converged: sim_exit = True

# hold the simulation window to exit manually
input("role assignment finished, press <ENTER> to exit")



