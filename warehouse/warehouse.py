from warehouse.item import Item
from warehouse.robot import Robot
from warehouse.utils import *
import numpy as np
from gym import spaces
import time
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import networkx as nx
import csv

class Warehouse(object):
    """
    warehouse environment
    """

    ACTIONS = {0: 'UP',
               1: 'DOWN',
               2: 'LEFT',
               3: 'RIGHT'}

    def __init__(self, seed=0):
        parameters = read_parameters('warehouse.yaml')
        # parameters = parse_arguments()
        self.n_columns = parameters['n_columns']
        self.n_rows = parameters['n_rows']
        self.n_robots_row = parameters['n_robots_row']
        self.n_robots_column = parameters['n_robots_column']
        self.distance_between_shelves = parameters['distance_between_shelves']
        self.robot_domain_size = parameters['robot_domain_size']
        self.prob_item_appears = parameters['prob_item_appears']
        # The learning robot
        self.learning_robot_id = parameters['learning_robot_id']
        self.max_episode_length = parameters['n_steps_episode']
        self.obs_type = parameters['obs_type']
        self.items = []
        self.img = None
        self.seed_value = seed
        self.parameters = parameters
        self.seed(seed)
        self.i = 0

    ############################## Override ###############################

    def reset(self):
        """
        Resets the environment's state
        """
        self.robot_id = 0
        self._place_robots()
        self.item_id = 0
        self.n_items_collected = 0
        self.items = []
        self._add_items()
        self.episode_length = 0
        reward = 0
        done = False
        return [reward, reward], done

    def step(self, actions):
        """
        Performs a single step in the environment.
        """ 
        self._robots_act(actions)
        reward = self._compute_reward()
        self._remove_items()
        self._add_items()
        self.episode_length += 1
        done = (self.max_episode_length <= self.episode_length)
        if self.parameters['render']:
            self.render(self.parameters['render_delay'])
        return [reward, reward], done

    @property
    def observation_space(self):
        return None

    @property
    def action_space(self):
        """
        Returns A gym dict containing the number of action choices for all the
        agents in the environment
        """
        n_actions = spaces.Discrete(len(self.ACTIONS))
        action_dict = {robot.get_id:n_actions for robot in self.robots}
        action_space = spaces.Dict(action_dict)
        action_space.n = 4
        return action_space

    def render(self, delay=0.5):
        """
        Renders the environment
        """
        bitmap = self._get_state()
        # position = self.robots[self.learning_robot_id].get_position
        # bitmap[position[0], position[1], 1] += 1
        im = bitmap[:, :, 0] - 2*bitmap[:, :, 1]
        if self.img is None:
            fig,ax = plt.subplots(1)
            self.img = ax.imshow(im, vmin=-2, vmax=1)
            for robot_id, robot in enumerate(self.robots):
                domain = robot.get_domain
                y = domain[0]
                x = domain[1]
                # if robot_id == self.learning_robot_id:
                #     color = 'r'
                #     linestyle='-'
                #     linewidth=2
                # else:
                color = 'k'
                linestyle=':'
                linewidth=1
                rect = patches.Rectangle((x-0.5, y-0.5), self.robot_domain_size[0],
                                         self.robot_domain_size[1], linewidth=linewidth,
                                         edgecolor=color, linestyle=linestyle,
                                         facecolor='none')
                ax.add_patch(rect)
                self.img.axes.get_xaxis().set_visible(False)
                self.img.axes.get_yaxis().set_visible(False)
        else:
            self.img.set_data(im)
        plt.pause(delay)
        plt.draw()
        # plt.savefig('../video/' + str(self.i))
        # self.i += 1

    def close(self):
        pass

    def seed(self, seed=None):
        if seed is not None:
            np.random.seed(seed)

    def get_dset(self):
        state = self._get_state()
        robot = self.robots[self.learning_robot_id]
        obs = robot.observe(state, 'vector')
        # dset = obs[49:]
        dset = obs
        return dset
    
    def get_robot_loc_bitmap(self, robot_id):
        state = self._get_state()
        obs = self.robots[robot_id].observe(state, 'vector')
        loc_bitmap = obs[:49]
        return loc_bitmap

    def get_infs(self, prev_obs, obs):
        prev_items = prev_obs[49:]
        items = obs[49:]
        bitmap = np.reshape(obs[:49], (7,7))
        # robot_neighbors = self._get_robot_neighbors(self.learning_robot_id)
        infs =  np.array(prev_items) - np.array(items) - np.concatenate((bitmap[[0,-1], :].flatten(),bitmap[1:-1, [0,-1]].flatten()))
        infs = np.maximum(np.zeros_like(infs), infs)
        # for neighbor_id in robot_neighbors:
        #     loc_bitmap = self.get_robot_loc_bitmap(neighbor_id)
        #     infs = np.append(infs, loc_bitmap)
        return infs            

    def create_graph(self, robot):
        """
        Creates a graph of robot's domain in the warehouse. Nodes are cells in
        the robot's domain and edges represent the possible transitions.
        """
        graph = nx.Graph()
        for i in range(robot.get_domain[0], robot.get_domain[2]+1):
            for j in range(robot.get_domain[1], robot.get_domain[3]+1):
                cell = np.array([i, j])
                graph.add_node(tuple(cell))
                for neighbor in self._neighbors(cell):
                    graph.add_edge(tuple(cell), tuple(neighbor))
        return graph

    ######################### Private Functions ###########################

    def _place_robots(self):
        """
        Sets robots initial position at the begining of every episode
        """
        self.robots = []
        domain_rows = np.arange(0, self.n_rows, self.robot_domain_size[0]-1)
        domain_columns = np.arange(0, self.n_columns, self.robot_domain_size[1]-1)
        for i in range(self.n_robots_row):
            for j in range(self.n_robots_column):
                robot_domain = [domain_rows[i], domain_columns[j],
                                domain_rows[i+1], domain_columns[j+1]]
                robot_position = [robot_domain[0] + self.robot_domain_size[0]//2,
                                  robot_domain[1] + self.robot_domain_size[1]//2]
                self.robots.append(Robot(self.robot_id, robot_position,
                                         robot_domain))
                self.robot_id += 1

    def _add_items(self):
        """
        Add new items to the designated locations in the environment.
        """
        item_locs = None
        if len(self.items) > 0:
            item_locs = [item.get_position for item in self.items]
        for row in range(self.n_rows):
            if row % (self.distance_between_shelves) == 0:
                for column in range(self.n_columns):
                    loc = [row, column]
                    loc_free = True
                    region_free = True
                    if item_locs is not None:
                        # region = int(column//self.distance_between_shelves)
                        # columns_occupied = [item_loc[1] for item_loc in item_locs if item_loc[0] == row]
                        # regions_occupied = [int(column//self.distance_between_shelves) for column in columns_occupied]
                        # region_free = region not in regions_occupied
                        loc_free = loc not in item_locs
                    if np.random.uniform() < self.prob_item_appears and loc_free:
                        self.items.append(Item(self.item_id, loc))
                        self.item_id += 1
                        item_locs = [item.get_position for item in self.items]
            else:
                for column in range(0, self.n_rows, self.distance_between_shelves):
                    loc = [row, column]
                    loc_free = True
                    region_free = True
                    if item_locs is not None:
                        # region = int(row//self.distance_between_shelves)
                        # rows_occupied = [item_loc[0] for item_loc in item_locs if item_loc[1] == column]
                        # regions_occupied = [int(row//self.distance_between_shelves) for row in rows_occupied]
                        # region_free = region not in regions_occupied
                        loc_free = loc not in item_locs
                    if np.random.uniform() < self.prob_item_appears and loc_free:
                        self.items.append(Item(self.item_id, loc))
                        self.item_id += 1
                        item_locs = [item.get_position for item in self.items]

    def _get_state(self):
        """
        Generates a 3D bitmap: First layer shows the location of every item.
        Second layer shows the location of the robots.
        """
        state_bitmap = np.zeros([self.n_rows, self.n_columns, 2], dtype=np.int)
        for item in self.items:
            item_pos = item.get_position
            state_bitmap[item_pos[0], item_pos[1], 0] = 1 #item.get_waiting_time
        for robot in self.robots:
            robot_pos = robot.get_position
            state_bitmap[robot_pos[0], robot_pos[1], 1] = 1
        return state_bitmap

    def _get_observation(self, robot_id):
        """
        Generates the individual observation for every robot given the current
        state and the robot's designated domain.
        """
        state = self._get_state()
        observation1 = self.robots[0].observe(state, 'vector')
        observation2 = self.robots[1].observe(state, 'vector')
        observation = np.concatenate((observation1,observation2))
        return observation

    def _get_robot_neighbors(self, robot_id):
        """
        Gets robot's neighbors
        """
        neighbors = [robot_id + 1, robot_id + 1 + self.parameters['n_robots_row'],
                     robot_id + self.parameters['n_robots_row'],
                     robot_id - 1 + self.parameters['n_robots_row'],
                     robot_id - 1, robot_id - 1 - self.parameters['n_robots_row'],
                     robot_id - self.parameters['n_robots_row'],
                     robot_id - self.parameters['n_robots_row'] + 1]
        return neighbors

    def _robots_act(self, actions):
        """
        All robots take an action in the environment.
        """
        for action,robot in zip(actions, self.robots):
            robot.act(action)

    def _compute_reward(self):
        """
        Computes reward for the learning robot.
        """
        reward = 0
        for robot in self.robots:
            robot_pos = robot.get_position
            for item in self.items:
                item_pos = item.get_position
                if robot_pos[0] == item_pos[0] and robot_pos[1] == item_pos[1]:
                    reward += 1
                    self.n_items_collected += 1
        return reward


    def _remove_items(self):
        """
        Removes items collected by robots. Robots collect items by steping on
        them
        """
        for robot in self.robots:
            robot_pos = robot.get_position
            for item in self.items:
                item_pos = item.get_position
                if robot_pos[0] == item_pos[0] and robot_pos[1] == item_pos[1]:
                    self.items.remove(item)

    def _increase_item_waiting_time(self):
        """
        Increases items waiting time
        """
        for item in self.items:
            item.increase_waiting_time()

    def _neighbors(self, cell):
        return [cell + [0, 1], cell + [0, -1], cell + [1, 0], cell + [-1, 0]]
    
    def _find_intersection(self, robot_a, robot_b):
        robot_a_domain = self.robots[robot_a].get_domain
        robot_b_domain = self.robots[robot_b].get_domain
        robot_a_rows = set(range(robot_a_domain[0],robot_a_domain[2]+1))
        robot_a_columns = set(range(robot_a_domain[1],robot_a_domain[3]+1))
        robot_b_rows = set(range(robot_b_domain[0],robot_b_domain[2]+1))
        robot_b_columns = set(range(robot_b_domain[1],robot_b_domain[3]+1))
        int_rows = list(robot_a_rows.intersection(robot_b_rows)) - robot_a_domain[0]
        int_columns = list(robot_a_columns.intersection(robot_b_columns)) - robot_a_domain[1]
        return int_rows, int_columns

    def load_influence_model(self):
        self.influence._load_model()