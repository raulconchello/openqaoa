#   Copyright 2022 Entropica Labs
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from abc import ABC, abstractmethod
from collections import defaultdict, Counter

import networkx as nx
import numpy as np
import scipy
import itertools

from .helper_functions import convert2serialize, check_kwargs
from openqaoa.qaoa_parameters.operators import Hamiltonian


class Problem(ABC):
    @staticmethod
    @abstractmethod
    def random_instance(**kwargs):
        """
        Creates a random instance of the problem.

        Parameters
        ----------
        **kwargs:
            Required keyword arguments

        Returns
        -------
            A random instance of the problem.
        """
        pass


class QUBO:
    """
    Creates an instance of Quadratic Unconstrained Binary Optimization (QUBO)
    class, which offers a way to encode optimization problems.

    Parameters
    ----------
    n: int
        The number of variables in the representation.
    terms: List[Tuple[int, ...],List]
        The different terms in the QUBO encoding, indicating the different
        interactions between variables.
    weights: List[float]
        The list of weights (or coefficients) corresponding to each
        interaction defined in `terms`.
    clean_terms_and_weights: bool
        Boolean indicating whether terms and weights can be cleaned by
        combining similar terms.

    Returns
    -------
        An instance of the Quadratic Unconstrained Binary Optimization 
        (QUBO) class.
    """

    # Maximum number of terms allowed to enable the cleaning procedure
    TERMS_CLEANING_LIMIT = 5000

    def __init__(self, n, terms, weights, clean_terms_and_weights=False):

        # check-type for terms and weights
        if not isinstance(terms, list) and not isinstance(terms, tuple):
            raise TypeError(
                "The input parameter terms must be of type of list or tuple"
            )

        if not isinstance(weights, list) and not isinstance(weights, tuple):
            raise TypeError(
                "The input parameter weights must be of type of list or tuple"
            )

        for each_entry in weights:
            if not isinstance(each_entry, float) and not isinstance(each_entry, int):
                raise TypeError(
                    "The elements in weights list must be of type float or int."
                )

        terms = list(terms)
        weights = list(weights)

        # Check that terms and weights have matching lengths
        if len(terms) != len(weights):
            raise ValueError(
                "The number of terms and number of weights do not match")

        constant = 0
        try:
            constant_index = [i for i, term in enumerate(
                terms) if len(term) == 0][0]
            constant = weights.pop(constant_index)
            terms.pop(constant_index)
        except:
            pass

        # If the user wants to clean the terms and weights or if the number of
        # terms is not too big, we go through the cleaning process
        if clean_terms_and_weights or len(terms) <= QUBO.TERMS_CLEANING_LIMIT:
            self.terms, self.weights = QUBO.clean_terms_and_weights(
                terms, weights)
        else:
            self.terms, self.weights = terms, weights

        self.constant = constant
        self.n = n

    @property
    def n(self):
        return self._n

    @n.setter
    def n(self, input_n):

        if not isinstance(input_n, int):
            raise TypeError("The input parameter, n, has to be of type int")

        if input_n <= 0:
            raise TypeError(
                "The input parameter, n, must be a positive integer greater than 0"
            )

        self._n = input_n

    def asdict(self):
        return convert2serialize(self)

    @staticmethod
    def clean_terms_and_weights(terms, weights):
        """ Goes through the terms and weights and group them when possible"""
        # List to record the terms as sets
        unique_terms = []

        # Will record the weight for the unique terms (note that since Sets are
        # unhashable in Python, we use a dict with integers for the keys, that
        # are mapped with the corresponding indices of terms from unique_terms)
        new_weights_for_terms = defaultdict(float)

        # We do one pass over terms and weights
        for term, weight in zip(terms, weights):

            # Convert the term to a set
            term_set = set(term)

            # If this term is not yet recorded, we add it to the list of unique
            # terms and we use that it is the last element to find its index
            if term_set not in unique_terms:
                unique_terms.append(term_set)
                term_index = len(unique_terms) - 1

            # Else if the term is alreaddy recorded, we just need to retrieve
            # its index in the unique_terms list
            else:
                term_index = unique_terms.index(term_set)

            # Update the weight in the dictionary using the retrieved index
            new_weights_for_terms[term_index] += weight

        # Return terms and weights, making sure to convert the terms back to lists
        return (
            [list(term) for term in unique_terms],
            list(new_weights_for_terms.values()),
        )

    @staticmethod
    def random_instance(n, density=0.5, format_m="coo", max_abs_value=100):
        # Generate a random matrix (elements in [0, 1]) of type sparse
        random_matrix = scipy.sparse.rand(
            n, n, density=density, format=format_m)

        # Retrieve the indices of non-zero elements of the matrix as list of tuples
        terms = np.transpose(random_matrix.nonzero())

        # Get the matrix entries in a list, but scale the elements and
        # make them centered at 0 by subtracting 0.5
        weights = max_abs_value * (random_matrix.data - 0.5)

        # Return the terms and weights, taking care of converting to the correct types
        return QUBO(n, [list(map(int, i)) for i in terms], [float(i) for i in weights])

    @staticmethod
    def convert_qubo_to_ising(n, qubo_terms, qubo_weights):
        """Convert QUBO terms and weights to their Ising equivalent"""
        ising_terms, ising_weights = [], []
        constant_term = 0
        linear_terms = np.zeros(n)

        # Process the given terms and weights
        for term, weight in zip(qubo_terms, qubo_weights):

            if len(term) == 2:
                u, v = term

                if u != v:
                    ising_terms.append([u, v])
                    ising_weights.append(weight / 4)
                else:
                    constant_term += weight / 4

                linear_terms[term[0]] -= weight / 4
                linear_terms[term[1]] -= weight / 4
                constant_term += weight / 4
            elif len(term) == 1:
                linear_terms[term[0]] -= weight / 2
                constant_term += weight / 2
            else:
                constant_term += weight

        for variable, linear_term in enumerate(linear_terms):
            ising_terms.append([variable])
            ising_weights.append(linear_term)

        ising_terms.append([])
        ising_weights.append(constant_term)
        return ising_terms, ising_weights

    @property
    def hamiltonian(self):
        """
        Returns the Hamiltonian of the problem.
        """
        return Hamiltonian.classical_hamiltonian(
            self.terms, self.weights, self.constant
        )


class TSP(Problem):
    """
    The Traveling Salesman Problem (TSP) requires to find, given a list of cities and the distances between each pair of cities (or the cities coordinates), the shortest possible path that visits each city exactly once and returns to the origin city. Additionally, one can also specify how cities are connected together.
    Our implementation accepts three different kind of inputs:
    #. A list of the cities' coordinates and, optionally, a (directed) graph specifiying the connectivity between cities
    #. A distance matrix encoding distances between each pair of cities and, optionally, a (directed) graph specifiying the connectivity between cities
    #. A weighted (directed) graph specifiying the connectivity and the distance between cities

    Initializes a TSP object via three different methods:
    #. Give a list of coordinates for the cities and optionally the connectivity between them via a (directed) graph.
    #. Give a distance matrix and optionally the connectivity between cities via a (directed) graph.
    #. Directly give a (directed) weighted graph, where edge weights are interpreted as distances between cities

    Whenever no graph connectivity is specified, it is assumed that all cities are connected.

    Parameters
    ----------
    city_coordinates : Optional[List[Tuple[float, float]]]
        List containing the coordinates of each city.

    distance_matrix : Optional[List[List[float]]]
        Distance between cities given as list of list representing a matrix

    G: Optional[nx.Graph]
        Graph encoding the connectivity between cities (can be directed)

    A: Optional[float]
        Quadratic penalty coefficient to enforce that a path is a Hamiltonian cycle.

    B: Optional[float]
        Penalty coefficient which accounts for the path cost.

    Returns
    -------
    None
    """
    def __init__(self,
                 city_coordinates=None,
                 distance_matrix=None,
                 G=None,
                 A=None,
                 B=1,
                 ):
        # Initialization when a weighted graph is given
        if G is not None and nx.is_weighted(G):
            TSP.validate_graph(G)
            n_cities = len(G)
        else:
            # Initialization when cities coordinates are given
            if city_coordinates is not None:
                TSP.validate_coordinates(city_coordinates)
                n_cities = len(city_coordinates)
                distance_matrix = scipy.spatial.distance_matrix(
                    city_coordinates, city_coordinates)
            # Initialization when a distance matrix is given
            elif distance_matrix is not None:
                TSP.validate_distance_matrix(distance_matrix)
                n_cities = len(distance_matrix)
                distance_matrix = np.array(distance_matrix)
            # Raise error if no input is given
            else:
                raise ValueError(
                    'Input missing: city coordinates, distance matrix or (weighted graph) required')

            # Take into account graph connectivity if unweighted graph is given
            G = G if G else nx.complete_graph(n_cities)
            if n_cities != len(G):
                raise ValueError(
                    'Number of cities does not match the number of nodes in graph')

            # Set edge weights to be the distances between corresponding cities
            for (u, v) in G.edges():
                G[u][v]['weight'] = distance_matrix[u, v]

        # Set number of cities
        self.n_cities = n_cities

        # Set the graph, making sure it is directed (useful when looping over edges during QUBO creation)
        self._G = nx.DiGraph(G)

        # Set penalty coefficients if given, otherwise give default value
        self.A = A if A else 2 * distance_matrix.max()
        self.B = B

    @property
    def graph(self):
        return self._G

    @staticmethod
    def validate_coordinates(city_coordinates):
        """
        Makes the necessary check given some city coordinates.

        Parameters
        ----------
        input_coordinates : List[Tuple[float, float]]
            List containing the coordinates of each city.

        Returns
        -------
            None
        """
        if not isinstance(city_coordinates, list):
            raise TypeError("The coordinates should be a list")

        for each_entry in city_coordinates:
            if not isinstance(each_entry, tuple):
                raise TypeError(
                    "The coordinates should be contained in a tuple")

            for each_value in each_entry:
                if not isinstance(each_value, float) and not isinstance(
                    each_value, int
                ):
                    raise TypeError(
                        "The coordinates must be of type float or int")

    @staticmethod
    def validate_distance_matrix(distance_matrix):
        """
        Makes the necessary check given some distance matrix.

        Parameters
        ----------
        distance_matrix : List[List[float]]
            Distance between cities given as list of list representing a matrix

        Returns
        -------
            None
        """
        if not isinstance(distance_matrix, list):
            raise TypeError("The distance matrix should be a list")

        for each_entry in distance_matrix:
            if not isinstance(each_entry, list):
                raise TypeError(
                    "Each row in the distance matrix should be a list")

            for each_value in each_entry:
                if not isinstance(each_value, float) and not isinstance(
                    each_value, int
                ):
                    raise TypeError(
                        "The distance matrix entries must be of type float or int")

                if each_value < 0:
                    raise ValueError("Distances should be positive")

    @staticmethod
    def validate_graph(G):
        """
        Makes the necessary check given some (weighted) graph.

        Parameters
        ----------
        G: nx.Graph
            Graph encoding the connectivity between cities (can be directed)

        Returns
        -------
            None
        """
        # Set edge weights to be the distances between corresponding cities
        for (u, v, weight) in G.edges(data='weight'):
            print(weight)
            if not isinstance(weight, float) and not isinstance(
                weight, int
            ):
                raise TypeError(
                    "The edge weights must be of type float or int")

            if weight < 0:
                raise ValueError("Edge weights should be positive")

    @staticmethod
    def random_instance(**kwargs):
        """
        Creates a random instance of the Traveling Salesman problem with
        fully connected cities.

        Parameters
        ----------
        n_cities: int
            The number of cities in the TSP instance. This is a required 
            keyword argument.

        Returns
        -------
            A random instance of the Traveling Salesman problem.
        """
        n_cities = check_kwargs(["n_cities"], [None], **kwargs)[0]

        # Set a random number generator
        seed = kwargs.get("seed", None)
        seed = seed if isinstance(seed, int) else None
        rng = np.random.default_rng(seed)

        # Generate random coordinates in a box of size sqrt(n_cities) x sqrt(n_cities)
        box_size = np.sqrt(n_cities)
        city_coordinates = list(
            map(tuple, box_size * rng.random(size=(n_cities, 2))))
        return TSP(city_coordinates=city_coordinates)

    def terms_and_weights(self):
        """
        Returns the terms and weights used in the QUBO formulation of this TSP instance.
        The QUBO formulation used is the one presented in Section 7.2 in 
        https://arxiv.org/pdf/1302.5843.pdf, and sets the first city to be visited to be
        the first city in order to reduce the number of variables.

        Returns
        -------
        Tuple[List[List[int]], List[float]]
            Tuple containing a list with the terms and a list with the corresponding weights.
        """

        # Constants (flags) useful for the helper function below
        ZERO_VALUED_VARIABLE = -2
        ONE_VALUED_VARIABLE = -1

        def get_variable_index(v, j):
            """
            Returns the actual configuration index given the two indices v (city) and j (step), 
            to mirror the formulation given in https://arxiv.org/pdf/1302.5843.pdf. Whenever the 
            city or step probed is the first one, it can also return a flag saying whether the 
            variable is 0 (flag=-2) or 1 (flag=-1), since the first city is fixed to reduce the
            number of variables).
            """
            if j > self.n_cities+1 or v > self.n_cities:
                raise ValueError('Index out of bounds')

            # Whenever the step is the first one (or n+1 equivalently)
            if j == 1 or j == self.n_cities + 1:
                # If the city is the first one, we have x_{1, 1} = 1
                if v == 1:
                    variable_index = ONE_VALUED_VARIABLE
                # Else we have x_{v, 1} = 0
                else:
                    variable_index = ZERO_VALUED_VARIABLE

            # When step j>1 is given
            else:
                # If first node, then x_{1, j} = 0
                if v == 1:
                    variable_index = ZERO_VALUED_VARIABLE
                # Else return the index corresponding to variable x_{v, j}
                else:
                    variable_index = (j - 2) * (self.n_cities - 1) + (v - 2)

            return variable_index

        # Init the various terms
        constant_term = 0
        single_terms = []
        interaction_terms = []

        # Constraints ensuring that a city only appears once in the cycle, and that there is only one city per step
        # (note that it was simplified to account that the first city is always city 1)
        constant_term += 2 * self.A * (self.n_cities-1)

        for v in range(2, self.n_cities + 1):
            for j in range(2, self.n_cities + 1):
                single_terms.append(([get_variable_index(v, j)], -4 * self.A))

        for k in range(2, self.n_cities + 1):
            for l in range(2, self.n_cities + 1):
                for v in range(2, self.n_cities + 1):
                    interaction_terms.append(
                        ([get_variable_index(v, k), get_variable_index(v, l)], self.A))

        for j in range(2, self.n_cities + 1):
            for u in range(2, self.n_cities + 1):
                for v in range(2, self.n_cities + 1):
                    interaction_terms.append(
                        ([get_variable_index(u, j), get_variable_index(v, j)], self.A))

        # Constraint which penalizes going through edges which are not part of the graph
        for (u, v) in nx.complement(self.graph).edges():
            for j in range(1, self.n_cities + 1):
                interaction_terms.append(
                    ([get_variable_index(u+1, j), get_variable_index(v+1, j+1)], self.A))

        # Terms to account for the path cost
        for (u, v) in self.graph.edges():
            for j in range(1, self.n_cities + 1):
                interaction_terms.append(([get_variable_index(
                    u+1, j), get_variable_index(v+1, j+1)], self.B * self.graph[u][v]['weight']))

        # Filtering linear and quadratic terms such that variables which are fixed (and have been flagged)
        # can be processed accordingly
        filtered_interaction_terms = []
        for interaction, weight in single_terms + interaction_terms:
            # If the term is non-zero (so no flag=-2 is present), we should consider it
            if ZERO_VALUED_VARIABLE not in interaction:
                # If the same variable appears in a quadratic term, it becomes a linear term
                if len(interaction) == 2 and interaction[0] == interaction[1]:
                    interaction.pop()

                # Update interaction to reduce the degree of a term if some variables are set to 1
                # (that is remove all flag=-1)
                interaction = list(
                    filter(lambda a: a != ONE_VALUED_VARIABLE, interaction))

                # Add the updated term
                filtered_interaction_terms.append((interaction, weight))

        # Unzip to retrieve terms and weights in separate sequences
        return tuple(zip(*(filtered_interaction_terms + [([], constant_term)])))

    def get_qubo_problem(self):
        """
        Returns the QUBO encoding of this problem.

        Returns
        -------
            The QUBO encoding of this problem.
        """
        n = (self.n_cities - 1) ** 2
        terms, weights = self.terms_and_weights()

        # Convert to Ising equivalent since variables are in {0, 1} rather than {-1, 1}
        ising_terms, ising_weights = QUBO.convert_qubo_to_ising(
            n, terms, weights)
        return QUBO(n, ising_terms, ising_weights)


class NumberPartition(Problem):
    """
    Creates an instance of the Number Partitioning problem.

    Parameters
    ----------
    numbers: List[int]
        The list of numbers to be partitioned.

    Returns
    -------
        An instance of the Number Partitioning problem.
    """

    def __init__(self, numbers=None):
        # Set the numbers to be partitioned. If not given, generate a random list with integers
        self.numbers = numbers
        self.n_numbers = None if numbers == None else len(self.numbers)

    @property
    def numbers(self):
        return self._numbers

    @numbers.setter
    def numbers(self, input_numbers):

        if not isinstance(input_numbers, list):
            raise TypeError("The input parameter, numbers, has to be a list")

        for each_entry in input_numbers:
            if not isinstance(each_entry, int):
                raise TypeError(
                    "The elements in numbers list must be of type int.")

        self._numbers = input_numbers

    @staticmethod
    def random_instance(**kwargs):
        """
        Creates a random instance of the Number Partitioning problem.

        Parameters
        ----------
        n_numbers: int
            The number of numbers to be partitioned. This is a required 
            keyword argument.

        Returns
        -------
            A random instance of the Number Partitioning problem.
        """
        n_numbers = check_kwargs(["n_numbers"], [None], **kwargs)

        # Set a random number generator
        seed = kwargs.get("seed", None)
        seed = seed if isinstance(seed, int) else None
        rng = np.random.default_rng(seed)

        numbers = list(map(int, rng.integers(1, 10, size=n_numbers)))
        return NumberPartition(numbers)

    def get_qubo_problem(self):
        """
        Returns the QUBO encoding of this problem.

        Returns
        -------
            The QUBO encoding of this problem.
        """
        terms = []
        weights = []
        constant_term = 0

        # Consider every pair of numbers (ordered)
        for i in range(self.n_numbers):
            for j in range(i, self.n_numbers):

                # If i equals j, then whatever random sign we choose, if we square
                # it we can back 1. So we have a constant term.
                if i == j:
                    constant_term += self.numbers[i] * self.numbers[j]

                # Otherwise the weight is computed as being the product of the
                # numbers in the pair, multiplied by 2 (since we account for
                # both pair (i, j) and (j, i)
                else:
                    term = [i, j]
                    weight = 2 * self.numbers[i] * self.numbers[j]

                    terms.append(term)
                    weights.append(weight)

        # If the constant term is non-zero, we may add it to terms and weights
        if constant_term > 0:
            terms.append([])
            weights.append(constant_term)

        return QUBO(self.n_numbers, terms, weights)


class MaximumCut(Problem):
    """
    Creates an instance of the Maximum Cut problem.

    Parameters
    ----------
    G: nx.Graph
        The input graph as NetworkX graph instance.

    Returns
    -------
        An instance of the Maximum Cut problem.
    """

    DEFAULT_EDGE_WEIGHT = 1.0

    def __init__(self, G):

        self.G = G

    @property
    def G(self):
        return self._G

    @G.setter
    def G(self, input_networkx_graph):

        if not isinstance(input_networkx_graph, nx.Graph):
            raise TypeError("Input problem graph must be a networkx Graph.")

        # Relabel nodes to integers starting from 0
        mapping = dict(
            zip(input_networkx_graph, range(
                input_networkx_graph.number_of_nodes()))
        )
        self._G = nx.relabel_nodes(input_networkx_graph, mapping)

    @staticmethod
    def random_instance(**kwargs):
        """
        Creates a random instance of the Maximum Cut problem, whose graph is
        random following the Erdos-Renyi model.

        Parameters
        ----------
        **kwargs:
        Required keyword arguments are:

            n_nodes: int
                The number of nodes (vertices) in the graph.
            edge_probability: float
                The probability with which an edge is added to the graph.

        Returns
        -------
            A random instance of the Maximum Cut problem.
        """
        n_nodes, edge_probability = check_kwargs(
            ["n_nodes", "edge_probability"], [None, None], **kwargs
        )
        seed = kwargs.get("seed", None)

        G = nx.generators.random_graphs.fast_gnp_random_graph(
            n=n_nodes, p=edge_probability, seed=seed
        )
        return MaximumCut(G)

    def get_qubo_problem(self):
        """
        Returns the QUBO encoding of this problem.

        Returns
        -------
            The QUBO encoding of this problem.
        """
        # Iterate over edges (with weight) and store accordingly
        terms = []
        weights = []

        for u, v, edge_weight in self.G.edges(data="weight"):
            terms.append([u, v])

            # We expect the edge weight to be given in the attribute called
            # "weight". If it is None, assume a weight of 1.0
            weights.append(
                edge_weight if edge_weight else MaximumCut.DEFAULT_EDGE_WEIGHT
            )

        return QUBO(self.G.number_of_nodes(), terms, weights)


class Knapsack(Problem):
    """
    Creates an instance of the Kanpsack problem.

    Parameters
    ----------
    values: List[int]
        The values of the items that can be placed in the kanpsack.
    weights: List[int]
        The weight of the items that can be placed in the knapsack.
    weight_capacity: int
        The maximum weight the knapsack can hold.
    penalty: float
        Penalty for the weight constraint.

    Returns
    -------
        An instance of the Knapsack problem.
    """

    def __init__(self, values, weights, weight_capacity, penalty):
        # Check whether the input is valid. Number of values should match the number of weights.
        if len(values) != len(weights):
            raise ValueError(
                "Number of items does not match given value and weights")

        self.values = values
        self.weights = weights
        self.weight_capacity = weight_capacity
        self.penalty = penalty
        self.n_items = len(weights)

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, input_values):

        if not isinstance(input_values, list):
            raise TypeError("The input parameter, values, has to be a list")

        for each_entry in input_values:
            if not isinstance(each_entry, int):
                raise TypeError(
                    "The elements in values list must be of type int.")

        self._values = input_values

    @property
    def weights(self):
        return self._weights

    @weights.setter
    def weights(self, input_weights):

        if not isinstance(input_weights, list):
            raise TypeError("The input parameter, weights, has to be a list")

        for each_entry in input_weights:
            if not isinstance(each_entry, int):
                raise TypeError(
                    "The elements in weights list must be of type int.")

        self._weights = input_weights

    @property
    def weight_capacity(self):
        return self._weight_capacity

    @weight_capacity.setter
    def weight_capacity(self, input_weight_capacity):

        if not isinstance(input_weight_capacity, int):
            raise TypeError(
                "The input parameter, weight_capacity, has to be of type int"
            )

        if input_weight_capacity <= 0:
            raise TypeError(
                "The input parameter, weight_capacity, must be a positive integer greater than 0"
            )

        self._weight_capacity = input_weight_capacity

    @property
    def penalty(self):
        return self._penalty

    @penalty.setter
    def penalty(self, input_penalty):

        if not isinstance(input_penalty, int) and not isinstance(input_penalty, float):
            raise TypeError(
                "The input parameter, penalty, has to be of type float or int"
            )

        self._penalty = input_penalty

    @staticmethod
    def random_instance(**kwargs):
        """
        Creates a random instance of the Knapsack problem.

        Parameters
        ----------
        n_items: int
            The number of items that can be placed in the knapsack.

        Returns
        -------
            A random instance of the Knapsack problem.
        """
        n_items = check_kwargs(["n_items"], [None], **kwargs)[0]

        # Set a random number generator
        seed = kwargs.get("seed", None)
        seed = seed if isinstance(seed, int) else None
        rng = np.random.default_rng(seed)

        values = list(map(int, rng.integers(1, n_items, size=n_items)))
        weights = list(map(int, rng.integers(1, n_items, size=n_items)))

        min_weights = np.min(weights)
        max_weights = np.max(weights)

        if min_weights != max_weights:
            weight_capacity = int(rng.integers(
                min_weights * n_items, max_weights * n_items
            ))
        else:
            weight_capacity = int(rng.integers(
                max_weights, max_weights * n_items))

        penalty = 2 * np.max(values)
        return Knapsack(values, weights, weight_capacity, int(penalty))

    def terms_and_weights(self):
        n_variables_slack = int(np.ceil(np.log2(self.weight_capacity)))
        n_variables = self.n_items + n_variables_slack

        # Edges between variables to represent slack value (the s_j's)
        edges_slacks = itertools.combinations(range(n_variables_slack), 2)
        edges_slacks_with_weights = [
            (list(e), 2 * self.penalty * (2 ** e[0]) * (2 ** e[1]))
            for e in edges_slacks
        ]

        # Edges between decision variables for weights (the x_i's)
        edges_decision_vars = itertools.combinations(
            range(n_variables_slack, n_variables), 2
        )
        edges_decision_vars_with_weights = [
            (
                list(e),
                2
                * self.penalty
                * self.weights[e[0] - n_variables_slack]
                * self.weights[e[1] - n_variables_slack],
            )
            for e in edges_decision_vars
        ]

        # Edges between decisions and variables to represent slack value (the x_i's and s_j's)
        edges_slacks_decision_vars = itertools.product(
            range(n_variables_slack), range(n_variables_slack, n_variables)
        )
        edges_slacks_decision_vars_with_weights = [
            (
                list(e),
                2 * self.penalty * (2 ** e[0]) *
                self.weights[e[1] - n_variables_slack],
            )
            for e in edges_slacks_decision_vars
        ]

        # Linear terms for the variables to represent slack value (s_j's)
        single_interaction_slacks = [
            ([i], self.penalty * (2 ** (2 * i) - 2 * self.weight_capacity * 2 ** i))
            for i in range(n_variables_slack)
        ]

        # Linear terms for the decision variables (the x_i's)
        single_interaction_decisions_vars = [
            (
                [i],
                self.penalty * self.weights[i - n_variables_slack] ** 2
                - 2
                * self.penalty
                * self.weight_capacity
                * self.weights[i - n_variables_slack]
                - self.values[i - n_variables_slack],
            )
            for i in range(n_variables_slack, n_variables)
        ]

        # The constant term
        constant_term = [([], self.penalty * self.weight_capacity ** 2)]

        # Unzip to retrieve terms and weights in separate sequences
        return tuple(
            zip(
                *(
                    edges_slacks_with_weights
                    + edges_decision_vars_with_weights
                    + edges_slacks_decision_vars_with_weights
                    + single_interaction_slacks
                    + single_interaction_decisions_vars
                    + constant_term
                )
            )
        )

    def get_qubo_problem(self):
        """
        Returns the QUBO encoding of this problem.

        Returns
        -------
            The QUBO encoding of this problem.
        """
        n_variables_slack = int(np.ceil(np.log2(self.weight_capacity)))
        n = self.n_items + n_variables_slack
        terms, weights = self.terms_and_weights()

        # Convert to Ising equivalent since variables are in {0, 1} rather than {-1, 1}
        ising_terms, ising_weights = QUBO.convert_qubo_to_ising(
            n, terms, weights)
        return QUBO(n, ising_terms, ising_weights)


class SlackFreeKnapsack(Knapsack):
    """
    A slack variable free approach to the Knapsack problem Hamiltonian. 
    The Hamiltonian consists of decision qubits with a quadratic penalty term centred
    on `W`, i.e. the maximum Knapsack Capacity.

    Creates an instance of the SlackFreeKanpsack problem.

    Parameters
    ----------
    values: List[int]
        The values of the items that can be placed in the kanpsack.
    weights: List[int]
        The weight of the items that can be placed in the knapsack.
    weight_capacity: int
        The maximum weight the knapsack can hold.
    penalty: float
        Penalty for the weight constraint.

    Returns
    -------
        An instance of the SlackFreeKnapsack problem.
    """

    def __init__(self, values, weights, weight_capacity, penalty):

        super().__init__(values, weights, weight_capacity, penalty)

    @staticmethod
    def random_instance(**kwargs):
        """
        Creates a random instance of the Knapsack problem.

        Parameters
        ----------
        n_items: int
            The number of items that can be placed in the knapsack.

        Returns
        -------
            A random instance of the Knapsack problem.
        """
        n_items = check_kwargs(["n_items"], [None], **kwargs)[0]

        # Set a random number generator
        seed = kwargs.get("seed", None)
        seed = seed if isinstance(seed, int) else None
        rng = np.random.default_rng(seed)

        values = list(map(int, rng.integers(1, n_items, size=n_items)))
        weights = list(map(int, rng.integers(1, n_items, size=n_items)))

        min_weights = np.min(weights)
        max_weights = np.max(weights)
        if min_weights != max_weights:
            weight_capacity = int(rng.integers(
                min_weights * n_items, max_weights * n_items
            ))
        else:
            weight_capacity = int(rng.integers(
                max_weights, max_weights * n_items))

        penalty = 2 * np.max(values)
        return SlackFreeKnapsack(values, weights, weight_capacity, int(penalty))

    def terms_and_weights(self):
        """
        Implementation of single and two-qubit terms in the slack-free Hamiltonian 
        for the Knapsack problem. 
        """

        n_variables = self.n_items

        # Edges between decision variables for weights (the x_i's)
        edges_decision_vars = itertools.combinations(range(n_variables), 2)
        edges_decision_vars_with_weights = [
            (list(e), 2 * self.penalty *
             self.weights[e[0]] * self.weights[e[1]])
            for e in edges_decision_vars
        ]

        # Linear terms for the decision variables (the x_i's)
        single_interaction_decisions_vars = [
            (
                [i],
                self.penalty * self.weights[i] ** 2
                - 2 * self.penalty * self.weight_capacity * self.weights[i]
                - self.values[i],
            )
            for i in range(n_variables)
        ]

        # The constant term
        constant_term = [([], self.penalty * self.weight_capacity ** 2)]

        # Unzip to retrieve terms and weights in separate sequences
        return tuple(
            zip(
                *(
                    edges_decision_vars_with_weights
                    + single_interaction_decisions_vars
                    + constant_term
                )
            )
        )

    def get_qubo_problem(self):
        """
        Returns the QUBO encoding of this problem.

        Returns
        -------
            The QUBO encoding of this problem.
        """
        n = self.n_items
        terms, weights = self.terms_and_weights()

        # Convert to Ising equivalent since variables are in {0, 1} rather than {-1, 1}
        ising_terms, ising_weights = QUBO.convert_qubo_to_ising(
            n, terms, weights)
        return QUBO(n, ising_terms, ising_weights)


class MinimumVertexCover(Problem):
    """
    Creates an instance of the Minimum Vertex Cover problem.

    Parameters
    ----------
    G: nx.Graph
        The input graph as NetworkX graph instance.
    field: float
        The strength of the artificial field minimizing the size of the cover.
    penalty: float
        The strength of the penalty enforcing the cover constraint.

    Returns
    -------
    An instance of the Minimum Vertex Cover problem.
    """

    def __init__(self, G, field, penalty):

        self.G = G
        self.field = field
        self.penalty = penalty

    @property
    def G(self):
        return self._G

    @G.setter
    def G(self, input_networkx_graph):

        if not isinstance(input_networkx_graph, nx.Graph):
            raise TypeError("Input problem graph must be a networkx Graph.")

        # Relabel nodes to integers starting from 0
        mapping = dict(
            zip(input_networkx_graph, range(
                input_networkx_graph.number_of_nodes()))
        )
        self._G = nx.relabel_nodes(input_networkx_graph, mapping)

    @property
    def field(self):
        return self._field

    @field.setter
    def field(self, input_field):

        if not isinstance(input_field, int) and not isinstance(input_field, float):
            raise TypeError(
                "The input parameter, field, has to be of type float or int"
            )

        self._field = input_field

    @property
    def penalty(self):
        return self._penalty

    @penalty.setter
    def penalty(self, input_penalty):

        if not isinstance(input_penalty, int) and not isinstance(input_penalty, float):
            raise TypeError(
                "The input parameter, penalty, has to be of type float or int"
            )

        self._penalty = input_penalty

    @staticmethod
    def random_instance(**kwargs):
        """
        Creates a random instance of the Minimum Vertex Cover problem, whose graph is
        random following the Erdos-Renyi model. By default the artificial field is
        set to 1.0 and the default penalty os taken to be 10 times larger.

        Parameters
        ----------
        **kwargs:
            Required keyword arguments are:

            n_nodes: int
                The number of nodes (vertices) in the graph.
            edge_probability: float
                The probability with which an edge is added to the graph.

        Returns
        -------
        A random instance of the Minimum Vertex Cover problem.
        """

        n_nodes, edge_probability = check_kwargs(
            ["n_nodes", "edge_probability"], [None, None], **kwargs
        )
        seed = kwargs.get("seed", None)
        G = nx.generators.random_graphs.fast_gnp_random_graph(
            n=n_nodes, p=edge_probability, seed=seed
        )

        DEFAULT_FIELD = 1.0
        DEFAULT_PENALTY = 10

        return MinimumVertexCover(G, DEFAULT_FIELD, DEFAULT_PENALTY)

    def terms_and_weights(self):
        """
        Creates the terms and weights for the Minimum Vertex Cover problem

        Returns
        -------
        terms_weights: tuple(list[list],list[float])
            Tuple containing list of terms and list of weights.
        """

        # Number of nodes
        n_nodes = self.G.number_of_nodes()

        # Number of edges
        edges = list(self.G.edges())

        # Connectivity of each node
        node_repetition = [e for edge in edges for e in edge]
        connectivity = dict(Counter(node_repetition))

        # Quadratic interation from penalty term
        quadratic_interaction = [(list(e), self.penalty / 4) for e in edges]

        # Linear terms from the artificial field
        linear_interaction = [
            ([i], -self.field / 2 + connectivity[i] * self.penalty / 4)
            if connectivity.get(i) is not None
            else ([i], -self.field / 2)
            for i in range(n_nodes)
        ]

        # Constant term
        constant_term = [([], n_nodes * self.field / 2 +
                          len(edges) * self.penalty / 4)]

        # Generate tuple containing a list with the terms and a list with the weights
        terms_weights = tuple(
            zip(*(quadratic_interaction + linear_interaction + constant_term))
        )

        # Unzip to retrieve terms and weights in separate sequences
        return terms_weights

    def get_qubo_problem(self):
        """
        Returns the QUBO encoding of this problem.

        Returns
        -------
        The QUBO encoding of this problem.
        """

        # Extract terms and weights from the problem definition
        terms, weights = self.terms_and_weights()

        return QUBO(self.G.number_of_nodes(), list(terms), list(weights))


class ShortestPath(Problem):
    """
    Creates an instance of the Shortest Path problem.

    Parameters
    ----------
    G: nx.Graph
        The input graph as NetworkX graph instance.
    source: int
        The index of the source node.
    dest: int
        The index of the destination node.

    Returns
    -------
        An instance of the Shortest Path problem.
    """

    def __init__(self, G, source, dest):

        # Relabel nodes to integers starting from 0
        mapping = dict(zip(G, range(G.number_of_nodes())))
        self.G = nx.relabel_nodes(G, mapping)

        self.source = source
        self.dest = dest

        assert source in list(
            G.nodes), f"Source node not within nodes of input graph"
        assert dest in list(
            G.nodes
        ), f"Destination node not within nodes of input graph"
        assert source != dest, "Source and destination nodes cannot be the same"

    @staticmethod
    def random_instance(**kwargs):
        """
        Creates a random instance of the Shortest problem, whose graph is
        random following the Erdos-Renyi model. By default the node and edge 
        weights are set to 1.0 and the default constraint is taken to be as large.

        Parameters
        ----------
        **kwargs:
            Required keyword arguments are:

            n_nodes: int
                The number of nodes (vertices) in the graph.
            edge_probability: float
                The probability with which an edge is added to the graph.

        Returns
        -------
        A random instance of the Shortest Path problem.
        """

        n_nodes, edge_probability, seed, source, dest = check_kwargs(
            ["n_nodes", "edge_probability", "seed", "source", "dest"],
            [None, None, 1234, 0, 1],
            **kwargs,
        )
        G = nx.generators.random_graphs.fast_gnp_random_graph(
            n=n_nodes, p=edge_probability, seed=seed
        )

        DEFAULT_WEIGHTS = 1.0

        for (u, v) in G.edges():
            G.edges[u, v]["weight"] = DEFAULT_WEIGHTS
        for w in G.nodes():
            G.nodes[w]["weight"] = DEFAULT_WEIGHTS

        return ShortestPath(G, source, dest)

    def terms_and_weights(self):
        """
        Creates the terms and weights for the Shortest Path problem

        Returns
        -------
        terms_weights: tuple(list[list],list[float])
            Tuple containing list of terms and list of weights
        """
        s = self.source
        d = self.dest
        n_nodes = self.G.number_of_nodes()
        n_edges = self.G.number_of_edges()

        # # Linear terms due to node weights
        #     # For loop version
        #     node_terms_weights = []
        #     for i in range(n_nodes):
        #         if i not in [s, d]:
        #             shift = int(i>s)+int(i>d)
        #             node_terms_weights.append(([i-shift], self.G.nodes[i]['weight']))
        node_terms_weights = [
            ([i - (int(i > s) + int(i > d))], self.G.nodes[i]["weight"])
            for i in range(n_nodes)
            if i not in [s, d]
        ]

        # Linear terms due to edge weights (shift of n_nodes-2 since we removed 2 nodes)
        #     # For loop version
        #     edge_terms_weights = []
        #     for i, (u,v) in enumerate(self.G.edges()):
        #         edge_terms_weights.append(([i+n_nodes-2], self.G.edges[u,v]['weights']))
        edge_terms_weights = [
            ([i + n_nodes - 2], self.G.edges[u, v]["weight"])
            for i, (u, v) in enumerate(self.G.edges())
        ]

        # Source flow constraint
        #     # For loop version
        #     start_flow_terms_weights = []
        #     for i, x in enumerate(self.G.edges()):
        #         for j, y in enumerate(self.G.edges()):
        #             if s in x and s in y:
        #                 if i == j:
        #                     start_flow_terms_weights.append(([i+n_nodes-2], -1))
        #                 else:
        #                     start_flow_terms_weights.append(([i+n_nodes-2,j+n_nodes-2], 1))
        start_flow_terms_weights = [
            ([i + n_nodes - 2], -1)
            if i == j
            else ([i + n_nodes - 2, j + n_nodes - 2], 1)
            for i, x in enumerate(self.G.edges())
            for j, y in enumerate(self.G.edges())
            if (s in x and s in y)
        ]

        # Destination flow constraint
        #     # For loop version
        #     dest_flow_terms_weights = []
        #     for i, x in enumerate(self.G.edges()):
        #         for j, y in enumerate(self.G.edges()):
        #             if d in x and d in y:
        #                 if i == j:
        #                     dest_flow_terms_weights.append(([i+n_nodes-2], -1))
        #                 else:
        #                     dest_flow_terms_weights.append(([i+n_nodes-2,j+n_nodes-2], 1))
        dest_flow_terms_weights = [
            ([i + n_nodes - 2], -1)
            if i == j
            else ([i + n_nodes - 2, j + n_nodes - 2], 1)
            for i, x in enumerate(self.G.edges())
            for j, y in enumerate(self.G.edges())
            if (d in x and d in y)
        ]

        # Path flow constraint
        path_flow_terms_weights = []
        for i in range(n_nodes):
            if i != d and i != s:
                shift = int(i > s) + int(i > d)
                path_flow_terms_weights.append(([i - shift], 4))
                for j, x in enumerate(self.G.edges()):
                    if i in x:
                        path_flow_terms_weights.append(
                            ([i - shift, j + n_nodes - 2], -4)
                        )
                    for k, y in enumerate(self.G.edges()):
                        if i in x and i in y:
                            if j == k:
                                path_flow_terms_weights.append(
                                    ([j + n_nodes - 2], 1))
                            else:
                                path_flow_terms_weights.append(
                                    ([j + n_nodes - 2, k + n_nodes - 2], 1)
                                )

        return tuple(
            zip(
                *(
                    node_terms_weights
                    + edge_terms_weights
                    + start_flow_terms_weights
                    + dest_flow_terms_weights
                    + path_flow_terms_weights
                )
            )
        )

    def get_qubo_problem(self):
        """
        Returns the QUBO encoding of this problem.

        Returns
        -------
        The QUBO encoding of this problem.
        """
        n = self.G.number_of_nodes() + self.G.number_of_edges() - 2
        # Extract terms and weights from the problem definition
        terms, weights = self.terms_and_weights()

        # Convert to Ising equivalent since variables are in {0, 1} rather than {-1, 1}
        ising_terms, ising_weights = QUBO.convert_qubo_to_ising(
            n, terms, weights)
        return QUBO(n, ising_terms, ising_weights)
