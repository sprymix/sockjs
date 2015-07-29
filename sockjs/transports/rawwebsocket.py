"""raw websocket transport."""
import asyncio
from aiohttp import web

from .base import Transport
from ..exceptions import SessionIsClosed
from ..protocol import FRAME_CLOSE, FRAME_MESSAGE


class RawWebSocketTransport(Transport):

    @asyncio.coroutine
    def server(self, ws, session):
        while True:
            try:
                frame, data = yield from session._wait(pack=False)
            except SessionIsClosed:
                break

            if frame == FRAME_MESSAGE:
                for text in data:
                    ws.send_str(text)
            elif frame == FRAME_CLOSE:
                try:
                    yield from ws.close(message='Go away!')
                finally:
                    yield from session._remote_closed()

    @asyncio.coroutine
    def client(self, ws, session):
        while True:
            msg = yield from ws.receive()

            if msg.tp == web.MsgType.text:
                if not msg.data:
                    continue

                yield from self.session._remote_message(msg.data)

            elif msg.tp == web.MsgType.close:
                yield from self.session._remote_close()
            elif msg.tp == web.MsgType.closed:
                yield from self.session._remote_closed()
                break

    @asyncio.coroutine
    def process(self):
        # start websocket connection
        ws = self.ws = web.WebSocketResponse()
        ws.start(self.request)

        try:
            yield from self.manager.acquire(self.session, self)
        except:  # should use specific exception
            yield from ws.close(message='Go away!')
            return ws

        server = asyncio.async(self.server(ws, self.session))
        client = asyncio.async(self.client(ws, self.session))
        try:
            yield from asyncio.wait(
                (server, client),
                return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield from self.session._remote_close(exc)
        finally:
            yield from self.manager.release(self.session)
            if not server.done():
                server.cancel()
            if not client.done():
                client.cancel()

        return ws
