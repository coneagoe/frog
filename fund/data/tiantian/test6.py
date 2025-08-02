import asyncio
import functools


def retry(times):
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            for i in range(times):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    print(e)

        return wrapped

    return wrapper


@retry(3)
async def bar():
    print("bar")


asyncio.run(bar())
