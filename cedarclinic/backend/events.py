import asyncio

listeners = set()


def subscribe():
    queue = asyncio.Queue()
    listeners.add(queue)
    return queue


def unsubscribe(queue):
    listeners.discard(queue)


def publish(event):
    for queue in listeners:
        queue.put_nowait(event)
