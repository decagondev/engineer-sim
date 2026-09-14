"""In-process Firestore stand-in for adapter tests. No network, no SDK."""
from __future__ import annotations

import copy


class _Snap:
    def __init__(self, ref, data):
        self.reference = ref
        self.id = ref.id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class _Query:
    def __init__(self, snaps):
        self._snaps = list(snaps)

    def limit(self, n: int) -> "_Query":
        return _Query(self._snaps[:n])

    def stream(self):
        return iter(self._snaps)

    def where(self, field, op, value) -> "_Query":
        out = []
        for snap in self._snaps:
            data = snap.to_dict() or {}
            got = data.get(field)
            if op == "==" and got == value:
                out.append(snap)
        return _Query(out)


class _Doc:
    def __init__(self, db: "FakeFirestore", path: tuple[str, ...]):
        self._db = db
        self._path = path
        self.id = path[-1]

    def get(self) -> _Snap:
        return _Snap(self, self._db._get(self._path))

    def set(self, data: dict, merge: bool = False) -> None:
        self._db._set(self._path, data, merge)

    def delete(self) -> None:
        self._db._delete(self._path)

    def collection(self, name: str) -> "_Col":
        return _Col(self._db, self._path + (name,))


class _Col:
    def __init__(self, db: "FakeFirestore", path: tuple[str, ...]):
        self._db = db
        self._path = path

    def document(self, doc_id: str) -> _Doc:
        return _Doc(self._db, self._path + (doc_id,))

    def stream(self):
        return iter(self._snaps())

    def where(self, field, op, value) -> _Query:
        return _Query(self._snaps()).where(field, op, value)

    def limit(self, n: int) -> _Query:
        return _Query(self._snaps()).limit(n)

    def _snaps(self) -> list[_Snap]:
        out = []
        for path, data in self._db._docs.items():
            if path[:-1] == self._path:
                out.append(_Snap(_Doc(self._db, path), data))
        return out


class FakeFirestore:
    def __init__(self) -> None:
        self._docs: dict[tuple[str, ...], dict] = {}

    def collection(self, name: str) -> _Col:
        return _Col(self, (name,))

    def _get(self, path: tuple[str, ...]):
        data = self._docs.get(path)
        return copy.deepcopy(data) if data is not None else None

    def _set(self, path: tuple[str, ...], data: dict, merge: bool) -> None:
        if merge and path in self._docs:
            merged = dict(self._docs[path])
            merged.update(data)
            self._docs[path] = merged
        else:
            self._docs[path] = dict(data)

    def _delete(self, path: tuple[str, ...]) -> None:
        self._docs.pop(path, None)
