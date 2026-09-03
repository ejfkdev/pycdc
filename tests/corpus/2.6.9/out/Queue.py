'''A multi-producer, multi-consumer queue.'''

from time import time as _time
from collections import deque
import heapq
__all__ = ['Empty', 'Full', 'Queue', 'PriorityQueue', 'LifoQueue']

class Empty(Exception):
    pass

class Full(Exception):
    pass

class Queue(()):
    pass

class PriorityQueue(Queue):
    pass

class LifoQueue(Queue):
    pass

