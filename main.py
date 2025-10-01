import asyncio
import uuid
from typing import List, Optional, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query

app = FastAPI()


class CRDTChar:
    def __init__(self, id, char, visible=True):
        self.id = id
        self.char = char
        self.visible = visible

    def to_dict(self):
        return {"id": self.id, "char": self.char, "visible": self.visible}


class CRDTDocument:
    def __init__(self):
        self.chars: List[CRDTChar] = []

    def to_snapshot(self):
        # return ordered list for clients to recontsruct state
        return [c.to_dict() for c in self.chars]

    def merge_insert(self, op_id, char, after_id: Optional[str]):

        # avoid duplicates
        if any(c.id == op_id for c in self.chars):
            return

        new_char = CRDTChar(op_id, char, visible=True)

        if after_id is None:
            # insert at beginning
            self.chars.insert(0, new_char)
            return

        # find the index of after_id
        for i, c in enumerate(self.chars):
            if c.id == after_id:
                self.chars.insert(i+1, new_char)
                return

        # if after_id not found , append to end fallback

        self.chars.append(new_char)

    def merge_delete(self, op_id):
        for c in self.chars:
            if c.id == op_id:
                c.visible = False
                return

    def get_text(self):
        return "".join([c.char for c in self.chars if c.visible])


class DocumentManager:
    # holds document in memory and connected through websocket per doc_id

    def __init__(self):
        # doc_id -> {"doc": CRDTDocument, "sockets": set(WebSocket), "clients": {client_id: {"username": str, "cursor": int}}}

        self.docs: Dict[str, Dict] = {}

    def ensure_doc(self, doc_id):
        if doc_id not in self.docs:
            self.docs[doc_id] = {"doc": CRDTDocument(), "sockets": set(), "clients": {}}

    async def connect(self, doc_id, websocket: WebSocket, client_id: str,  username: str):
        self.ensure_doc(doc_id)
        self.docs[doc_id]["sockets"].add(websocket)
        self.docs[doc_id]["clients"][client_id] = {"username": username, "cursor": 0}
        await self.broadcast_users(doc_id)

    async def disconnect(self, doc_id, websocket: WebSocket, client_id: str):
        if doc_id in self.docs:
            if websocket in self.docs[doc_id]['sockets']:
                self.docs[doc_id]['sockets'].remove(websocket)
            if client_id in self.docs[doc_id]['clients']:
                del self.docs[doc_id]['clients'][client_id]

            # cleanup if no clients remain
            if not self.docs[doc_id]['sockets']:
                # Optional: keep doc in memory or persist; here we keep it
                pass

            await self.broadcast_users(doc_id)

    async def broadcast(self, doc_id, message):
        """
        Broadcast message to all connected clients for doc_id.
        If a websocket is dead, remove it.
        """

        if doc_id not in self.docs:
            return

        sockets = list(self.docs[doc_id]["sockets"])
        to_remove = []
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            await self.disconnect(doc_id, ws, "")

    async def broadcast_users(self, doc_id):
        users = [
            {"id": cid, "username": meta["username"], "cursor": meta["cursor"]}
            for cid, meta in self.docs[doc_id]["clients"].items()
        ]
        await self.broadcast(doc_id, {"type": "user_list", "users": users})


manager = DocumentManager()


@app.websocket("/ws/{doc_id}")
async def websocket_endpoint(
    websocket: WebSocket, doc_id, client_id: Optional[str] = Query(None), username: Optional[str] = Query("Anonymous")
):

    await websocket.accept()
    await manager.connect(doc_id, websocket, client_id, username)

    # send initial snapshot
    snapshot = manager.docs[doc_id]["doc"].to_snapshot()
    await websocket.send_json({"type": "snapshot", "chars": snapshot})

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")

            if mtype == "insert":
                # client sends: {type:'insert', char: 'a', after: <id or null>, client_op_id: 'tmp-1'}

                char = msg['char']
                after = msg.get("after")  # can be done
                client_op_id = msg.get("client_op_id")

                server_id = str(uuid.uuid4())

                op = {
                    "type": "insert",
                    "id": server_id,
                    "char": char,
                    "after": after,
                    "client_op_id": client_op_id,
                    "author": client_id
                }

                # merge on server
                manager.docs[doc_id]["doc"].merge_insert(server_id, char, after)

                # broadcast to all clients (including sender)
                await manager.broadcast(doc_id, op)

            elif mtype == "delete":
                # client sends: {type:'delete', id: <server-assigned-id>}
                del_id = msg["id"]
                op = {"type": "delete", "id": del_id, "author": client_id}

                manager.docs[doc_id]["doc"].merge_delete(del_id)
                await manager.broadcast(doc_id, op)

            elif mtype == "cursor":
                # client sends: {type: "cursor", position: int}
                pos = msg.get("position", 0)
                if client_id in manager.docs[doc_id]["clients"]:
                    manager.docs[doc_id]["clients"][client_id]["cursor"] = pos

                await manager.broadcast(doc_id, {
                    "type": "cursor",
                    "user_id": client_id,
                    "username": username,
                    "position": pos
                })

            else:
                # unknown type - ignore or log
                await websocket.send_json({"type": "error", "msg": "unknown message type"})
    except WebSocketDisconnect:
        await manager.disconnect(doc_id, websocket, client_id)
    except Exception:
        await manager.disconnect(doc_id, websocket, client_id)
        raise
