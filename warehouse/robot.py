import numpy as np
import networkx as nx
import random
import math

class Robot():
    """
    A robot on the warehouse
    """
    ACTIONS = {'UP': 0,
               'DOWN': 1,
               'LEFT': 2,
               'RIGHT': 3}

    def __init__(self, robot_id, robot_position, robot_domain):
        """
        @param pos tuple (x,y) with initial robot position.
        Initializes the robot
        """
        self._id = robot_id
        self._pos = robot_position
        self._robot_domain = robot_domain
        self.items_collected = 0
        self.done = False
        self._graph = None
        self._action_space = 4
        self._action_mapping = {(-1, 0): self.ACTIONS.get('UP'),
                                (1, 0): self.ACTIONS.get('DOWN'),
                                (0, -1): self.ACTIONS.get('LEFT'),
                                (0, 1): self.ACTIONS.get('RIGHT')}

    @property
    def get_id(self):
        """
        returns the robot identifier
        """
        return self._id

    @property
    def get_position(self):
        """
        @return: (x,y) array with current robot position
        """
        return self._pos

    @property
    def get_domain(self):
        return self._robot_domain

    def observe(self, state, obs_type):
        """
        Retrieve observation from envrionment state
        """
        observation = state[self._robot_domain[0]: self._robot_domain[2]+1,
                            self._robot_domain[1]: self._robot_domain[3]+1, :]
        if obs_type == 'image':
            robot_loc = np.zeros_like(observation[:, :, 1])
            robot_loc[self._pos[0] - self._robot_domain[0], self._pos[1] - self._robot_domain[1]] = 1
            observation = observation[:,:,0] + -1*robot_loc
        else:
            item_vec = np.concatenate((observation[[0,-1], :, 0].flatten(),
                                      observation[1:-1, [0,-1], 0].flatten()))

            robot_loc = np.zeros_like(observation[:, :, 1])
            robot_loc[self._pos[0] - self._robot_domain[0], self._pos[1] - self._robot_domain[1]] = 1
            robot_loc = robot_loc.flatten()
            observation = np.concatenate((robot_loc, item_vec))
        return observation

    def act(self, action):
        """
        Take an action
        """
        if action == 0:
            new_pos = [self._pos[0] - 1, self._pos[1]]
        if action == 1:
            new_pos = [self._pos[0] + 1, self._pos[1]]
        if action == 2:
            new_pos = [self._pos[0], self._pos[1] - 1]
        if action == 3:
            new_pos = [self._pos[0], self._pos[1] + 1]
        self.set_position(new_pos)

    def set_position(self, new_pos):
        """
        @param new_pos: an array (x,y) with the new robot position
        """
        if self._robot_domain[0] <= new_pos[0] <= self._robot_domain[2] and \
           self._robot_domain[1] <= new_pos[1] <= self._robot_domain[3]:
            self._pos = new_pos

    def select_random_action(self):
        action = random.randint(0, self._action_space - 1)
        return action
    
    def select_naive_action(self, obs):
        """
        Take one step towards the closest item
        """
        if self._graph is None:
            self._graph = self._create_graph(obs)
            self._path_dict = dict(nx.all_pairs_dijkstra_path(self._graph))
        path = self._path_to_closest_item(obs)
        if path is None or len(path) < 2:
            action = random.randint(0, self._action_space - 1)
        else:
            action = self._get_first_action(path)
        return action
    
    def select_naive_action2(self, obs, items):
        """
        Take one step towards the oldest item
        """
        if self._graph is None:
            self._graph = self._create_graph(obs)
            self._path_dict = dict(nx.all_pairs_dijkstra_path(self._graph))
        items_robot_region = self._get_items_robot_region(items)
        path = self._path_to_oldest_item(items_robot_region)
        if path is None or len(path) < 2:
            action = random.randint(0, self._action_space - 1)
        else:
            action = self._get_first_action(path)
        return action

    def _create_graph(self, obs):
        """
        Creates a graph of robot's domain in the warehouse. Nodes are cells in
        the robot's domain and edges represent the possible transitions.
        """
        graph = nx.Graph()
        for index, _ in np.ndenumerate(obs):
            cell = np.array(index)
            graph.add_node(tuple(cell))
            for neighbor in self._neighbors(cell):
                graph.add_edge(tuple(cell), tuple(neighbor))
        return graph
    
    def _neighbors(self, cell):
        return [cell + [0, 1], cell + [0, -1], cell + [1, 0], cell + [-1, 0]]

    def _path_to_closest_item(self, obs):
        """
        Calculates the distance of every item in the robot's domain, finds the
        closest item and returns the path to that item.
        """
        min_distance = len(obs[:,0]) + len(obs[0,:])
        closest_item_path = None
        robot_pos = (self._pos[0]-self._robot_domain[0], self._pos[1]-self._robot_domain[1])
        for index, item in np.ndenumerate(obs):
            if item == 1:
                path = self._path_dict[robot_pos][index]
                distance = len(path) - 1
                if distance < min_distance:
                    min_distance = distance
                    closest_item_path = path
        return closest_item_path

    def _get_first_action(self, path):
        """
        Get first action to take in a given path
        """
        delta = tuple(np.array(path[1]) - np.array(path[0]))
        action = self._action_mapping.get(delta)
        return action

    def _path_to_oldest_item(self, items):
        """
        Returns the path to the oldest item in the robot's domain.
        """
        oldest_item_path = None
        min_waiting_time = math.inf
        for index, item in enumerate(items):
            waiting_time = item.get_waiting_time
            if waiting_time < min_waiting_time:
                min_waiting_time = waiting_time
                min_index = index
        if len(items) > 0:
            item_global_pos = items[min_index].get_position
            domain_size = self._robot_domain[2] - self._robot_domain[0] + 1
            item_relative_pos = (item_global_pos[0]-self._robot_domain[0], item_global_pos[1]-self._robot_domain[1])
            robot_pos = (self._pos[0]-self._robot_domain[0], self._pos[1]-self._robot_domain[1])
            oldest_item_path = self._path_dict[robot_pos][item_relative_pos]
        return oldest_item_path
    
    def _get_items_robot_region(self, items):
        """
        From a list of items returns the ones that are in the robot's region
        """
        items_robot_region = []
        for item in items:
            pos = item.get_position
            if (self._robot_domain[0] <= pos[0] <= self._robot_domain[2] and \
              self._robot_domain[1] <= pos[1] <= self._robot_domain[3]):
                items_robot_region.append(item)
        return items_robot_region
