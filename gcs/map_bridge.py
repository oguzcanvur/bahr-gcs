from __future__ import annotations

import json

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class MapBridge(QObject):
    polygon_changed = pyqtSignal(list)
    waypoint_moved = pyqtSignal(int, float, float)
    goto_selected = pyqtSignal(float, float)
    map_ready = pyqtSignal()

    @pyqtSlot()
    def onMapReady(self) -> None:
        self.map_ready.emit()

    @pyqtSlot(str)
    def onPolygonUpdated(self, payload: str) -> None:
        try:
            points = json.loads(payload)
        except json.JSONDecodeError:
            return
        if isinstance(points, list):
            self.polygon_changed.emit(points)

    @pyqtSlot(int, float, float)
    def onWaypointMoved(self, index: int, latitude: float, longitude: float) -> None:
        self.waypoint_moved.emit(index, latitude, longitude)

    @pyqtSlot(float, float)
    def onGotoSelected(self, latitude: float, longitude: float) -> None:
        self.goto_selected.emit(latitude, longitude)
