# -*- coding: utf-8 -*-
# Copyright (C) 2026 Mykhailo Krechkivskyi

#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from dataclasses import dataclass, field
import os
from typing import List, Optional

from qgis.core import QgsProject, Qgis, QgsLayerTreeGroup, QgsLayerTreeLayer
from qgis.PyQt.QtCore import Qt, QModelIndex, QTimer

from . import common


@dataclass
class ProjectInfo:
    folder_name: str
    folder_path: str
    katotth: str = ""
    file_names: List[str] = field(default_factory=list)
    group: Optional[object] = None
    layers: List[object] = field(default_factory=list)


class OpenedProjects:
    def __init__(self, iface=None, on_current_project_changed=None):
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects.__init__()")
        self.iface = iface
        self.on_current_project_changed = on_current_project_changed
        self.projects: List[ProjectInfo] = []
        self.current_project: Optional[object] = None
        self._connect_layer_tree()
        self._connect_selection()

    def reset(self) -> None:
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects.reset()")
        self.projects.clear()

    def new_project(self, folder_name: str, folder_path: str, katotth: str = "") -> ProjectInfo:
        if common.LOG:
            common.log_calls(
                common.logFile,
                f"OpenedProjects.new_project(folder_name={folder_name!r}, folder_path={folder_path!r}, katotth={katotth!r})",
            )
        folder_path = os.path.abspath(folder_path)
        file_names = self._list_files(folder_path)
        group = self._find_group(folder_name)
        layers = self._layers_in_group(group)
        info = ProjectInfo(
            folder_name=folder_name,
            folder_path=folder_path,
            katotth=katotth,
            file_names=file_names,
            group=group,
            layers=layers,
        )
        self._upsert(info)
        self._notify_current_project_changed(self.current_project)
        return info

    def remove_by_group(self, group: object) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects.remove_by_group(group={group!r})")
        if group is None:
            return
        self.projects = [project for project in self.projects if project.group is not group]
        self._handle_project_removed()

    def set_current_project_group(self, group: Optional[object]) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects.set_current_project_group(group={group!r})")
        self._set_current_project(group)

    def _upsert(self, info: ProjectInfo) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._upsert(info={info!r})")
        if info.group is not None:
            for index, project in enumerate(self.projects):
                if project.group is info.group:
                    self.projects[index] = info
                    return
        for index, project in enumerate(self.projects):
            if os.path.normcase(project.folder_path) == os.path.normcase(info.folder_path):
                self.projects[index] = info
                return
        self.projects.append(info)

    def _list_files(self, folder_path: str) -> List[str]:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._list_files(folder_path={folder_path!r})")
        try:
            return sorted(
                name
                for name in os.listdir(folder_path)
                if os.path.isfile(os.path.join(folder_path, name))
            )
        except Exception:
            return []

    def _find_group(self, folder_name: str) -> Optional[object]:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._find_group(folder_name={folder_name!r})")
        try:
            root = QgsProject.instance().layerTreeRoot()
        except Exception:
            return None
        if root is None:
            return None
        try:
            return root.findGroup(folder_name)
        except Exception:
            return None

    def _layers_in_group(self, group: Optional[object]) -> List[object]:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._layers_in_group(group={group!r})")
        if group is None:
            return []
        layers: List[object] = []
        try:
            for child in group.children():
                layer = getattr(child, "layer", None)
                if callable(layer):
                    layer_obj = layer()
                    if layer_obj is not None:
                        layers.append(layer_obj)
        except Exception:
            return layers
        return layers

    def _connect_layer_tree(self) -> None:
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects._connect_layer_tree()")
        try:
            root = QgsProject.instance().layerTreeRoot()
        except Exception:
            return
        if root is None:
            return
        signal = getattr(root, "removedChildren", None)
        if signal is None:
            return
        try:
            signal.connect(self._on_removed_children)
        except Exception:
            return

    def sync_existing_project_groups(self) -> None:
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects.sync_existing_project_groups()")
        try:
            root = QgsProject.instance().layerTreeRoot()
        except Exception:
            return
        if root is None:
            return
        def _walk(parent):
            try:
                children = parent.children()
            except Exception:
                return
            for child in children:
                is_group = getattr(child, "isGroup", None)
                if callable(is_group) and is_group():
                    try:
                        name = child.name()
                    except Exception:
                        name = ""
                    if name and self._is_katotth_name(name):
                        self._ensure_project_entry(child)
                    _walk(child)
        _walk(root)

    def _connect_selection(self) -> None:
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects._connect_selection()")
        if self.iface is None:
            return
        try:
            view = self.iface.layerTreeView()
        except Exception:
            return
        if view is None:
            return
        try:
            view.currentNodeChanged.connect(self._on_current_node_changed)
        except Exception:
            pass
        try:
            view.currentLayerChanged.connect(self._on_current_layer_changed)
        except Exception:
            pass
        try:
            selection_model = view.selectionModel()
        except Exception:
            selection_model = None
        if selection_model is not None:
            try:
                selection_model.currentChanged.connect(self._on_current_index_changed)
            except Exception:
                pass

    def _set_current_project(self, group: Optional[object]) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._set_current_project(group={group!r})")
        if group is not None and not self._is_katotth_group_name(group):
            group = None
        if group is not None:
            self._ensure_project_entry(group)
        if group is self.current_project:
            return
        self.current_project = group
        self._notify_current_project_changed(group)
        if group is None:
            return
        self._announce_current_group(group)

    def _announce_current_group(self, group: object) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._announce_current_group(group={group!r})")
        name = None
        try:
            name = group.name()
        except Exception:
            name = None
        if not name:
            return
        try:
            if self.iface is not None:
                self.iface.messageBar().pushMessage(
                    "GeoJsonUa",
                    f"Поточний проект {name}.",
                    level=Qgis.Info,
                    duration=5,
                )
        except Exception:
            return

    def _announce_no_active_project(self) -> None:
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects._announce_no_active_project()")
        try:
            if self.iface is not None:
                self.iface.messageBar().pushMessage(
                    "GeoJsonUa",
                    "Нема активного проекта.",
                    level=Qgis.Info,
                    duration=5,
                )
        except Exception:
            return

    def _notify_current_project_changed(self, group: Optional[object]) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._notify_current_project_changed(group={group!r})")
        if self.on_current_project_changed is None:
            return
        name = None
        if group is not None:
            try:
                name = group.name()
            except Exception:
                name = None
        try:
            self.on_current_project_changed(name)
        except Exception:
            return

    def _handle_project_removed(self) -> None:
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects._handle_project_removed()")
        self.current_project = None
        self._notify_current_project_changed(None)

        def _apply():
            self._clear_selection()
            self._announce_no_active_project()

        try:
            QTimer.singleShot(0, _apply)
        except Exception:
            _apply()

    def _node_to_group(self, node: Optional[object]) -> Optional[object]:
        if common.LOG:
            node_type = type(node).__name__ if node is not None else None
            common.log_calls(common.logFile, f"OpenedProjects._node_to_group(node_type={node_type})")
        if node is None:
            return None
        if isinstance(node, type):
            return None
        if isinstance(node, QgsLayerTreeGroup):
            return node
        try:
            if hasattr(node, "name") and hasattr(node, "children") and not callable(getattr(node, "layer", None)):
                return node
        except Exception:
            pass
        if isinstance(node, QgsLayerTreeLayer):
            parent = getattr(node, "parent", None)
            parent_node = parent() if callable(parent) else None
            while parent_node is not None:
                if isinstance(parent_node, QgsLayerTreeGroup):
                    return parent_node
                parent = getattr(parent_node, "parent", None)
                parent_node = parent() if callable(parent) else None
        return None

    def _model_index_to_node(self, model: object, index: object) -> Optional[object]:
        if common.LOG:
            common.log_calls(
                common.logFile,
                f"OpenedProjects._model_index_to_node(model={model!r}, index={index!r})",
            )
        if model is None or index is None:
            return None
        try:
            is_valid = getattr(index, "isValid", None)
            if callable(is_valid) and not is_valid():
                return None
        except Exception:
            return None
        if hasattr(model, "indexToNode"):
            try:
                return model.indexToNode(index)
            except Exception:
                return None
        if hasattr(model, "nodeFromIndex"):
            try:
                return model.nodeFromIndex(index)
            except Exception:
                return None
        return None

    def _index_to_node(self, view: object, index: object) -> Optional[object]:
        if common.LOG:
            common.log_calls(
                common.logFile,
                f"OpenedProjects._index_to_node(view={view!r}, index={index!r})",
            )
        if view is None or index is None:
            return None
        try:
            model = view.model()
        except Exception:
            model = None
        if model is None:
            return None
        # Proxy model mapping if available.
        try:
            if hasattr(model, "mapToSource") and hasattr(model, "sourceModel"):
                source_index = model.mapToSource(index)
                source_model = model.sourceModel()
                node = self._model_index_to_node(source_model, source_index)
                if node is not None:
                    return node
        except Exception:
            pass
        node = self._model_index_to_node(model, index)
        if node is not None:
            return node
        try:
            layer_tree_model = view.layerTreeModel()
        except Exception:
            layer_tree_model = None
        if layer_tree_model is not None and layer_tree_model is not model:
            return self._model_index_to_node(layer_tree_model, index)
        return None

    def _view_current_node(self, view: object) -> Optional[object]:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._view_current_node(view={view!r})")
        if view is None:
            return None
        current_node = getattr(view, "currentNode", None)
        if callable(current_node):
            try:
                return current_node()
            except Exception:
                return None
        return None

    def _view_current_layer(self, view: object) -> Optional[object]:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._view_current_layer(view={view!r})")
        if view is None:
            return None
        current_layer = getattr(view, "currentLayer", None)
        if callable(current_layer):
            try:
                return current_layer()
            except Exception:
                return None
        return None

    def _is_katotth_name(self, name: str) -> bool:
        if not name or name.startswith("old_"):
            return False
        base = name.split("_", 1)[0].upper()
        return len(base) == 19 and base.startswith("UA") and base[2:].isdigit()

    def _is_katotth_group_name(self, group: object) -> bool:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._is_katotth_group_name(group={group!r})")
        try:
            name = group.name()
        except Exception:
            return False
        return self._is_katotth_name(name)

    def _on_current_node_changed(self, current, previous) -> None:
        if common.LOG:
            common.log_calls(
                common.logFile,
                f"OpenedProjects._on_current_node_changed(current={current!r}, previous={previous!r})",
            )
        group = self._node_to_group(current)
        self._set_current_project(group)

    def _on_current_layer_changed(self, layer) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._on_current_layer_changed(layer={layer!r})")
        if layer is None:
            self._set_current_project(None)
            return
        try:
            root = QgsProject.instance().layerTreeRoot()
        except Exception:
            return
        if root is None:
            return
        try:
            node = root.findLayer(layer.id())
        except Exception:
            return
        group = self._node_to_group(node)
        self._set_current_project(group)

    def _on_current_index_changed(self, current, previous) -> None:
        if common.LOG:
            common.log_calls(
                common.logFile,
                f"OpenedProjects._on_current_index_changed(current={current!r}, previous={previous!r})",
            )
        if self.iface is None:
            return
        try:
            view = self.iface.layerTreeView()
        except Exception:
            return
        if view is None:
            return
        node = self._index_to_node(view, current)
        if node is None:
            node = self._view_current_node(view)
        if node is None:
            layer = self._view_current_layer(view)
            if layer is not None:
                try:
                    root = QgsProject.instance().layerTreeRoot()
                except Exception:
                    root = None
                if root is not None:
                    try:
                        node = root.findLayer(layer.id())
                    except Exception:
                        node = None
        group = self._node_to_group(node)
        name = None
        if group is None:
            name = self._index_display_name(view, current)
            if name and self._is_katotth_name(name):
                try:
                    root = QgsProject.instance().layerTreeRoot()
                except Exception:
                    root = None
                if root is not None:
                    try:
                        group = root.findGroup(name)
                    except Exception:
                        group = None
        if group is None:
            try:
                parent_index = current.parent()
            except Exception:
                parent_index = None
            while parent_index is not None and getattr(parent_index, "isValid", lambda: False)():
                parent_node = self._index_to_node(view, parent_index)
                group = self._node_to_group(parent_node)
                if group is not None:
                    break
                try:
                    parent_index = parent_index.parent()
                except Exception:
                    parent_index = None
        if group is not None and self._is_katotth_group_name(group):
            # Announce even if current_project does not change to show selected group.
            self._announce_current_group(group)
        elif name and self._is_katotth_name(name):
            self._announce_current_name(name)
        self._set_current_project(group)

    def _index_display_name(self, view: object, index: object) -> Optional[str]:
        if common.LOG:
            common.log_calls(
                common.logFile,
                f"OpenedProjects._index_display_name(view={view!r}, index={index!r})",
            )
        if view is None or index is None:
            return None
        try:
            data = index.data(Qt.DisplayRole)
            if data:
                return str(data)
        except Exception:
            pass
        try:
            model = view.model()
        except Exception:
            model = None
        if model is None:
            return None
        try:
            data = model.data(index, Qt.DisplayRole)
            if data:
                return str(data)
        except Exception:
            return None
        return None

    def _announce_current_name(self, name: str) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._announce_current_name(name={name!r})")
        try:
            if self.iface is not None:
                self.iface.messageBar().pushMessage(
                    "GeoJsonUa",
                    f"Поточний проект {name}.",
                    level=Qgis.Info,
                    duration=5,
                )
        except Exception:
            return

    def _ensure_project_entry(self, group: object) -> None:
        if group is None:
            return
        try:
            name = group.name()
        except Exception:
            return
        if not name or not self._is_katotth_name(name):
            return
        for project in self.projects:
            if project.group is group:
                return
        katotth = name.split("_", 1)[0].upper()
        info = ProjectInfo(
            folder_name=name,
            folder_path="",
            katotth=katotth,
            file_names=[],
            group=group,
            layers=self._layers_in_group(group),
        )
        self.projects.append(info)

    def _clear_selection(self) -> None:
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects._clear_selection()")
        if self.iface is None:
            return
        try:
            view = self.iface.layerTreeView()
        except Exception:
            return
        if view is None:
            return
        try:
            selection_model = view.selectionModel()
        except Exception:
            selection_model = None
        if selection_model is not None:
            try:
                selection_model.clearSelection()
            except Exception:
                pass
            try:
                selection_model.setCurrentIndex(QModelIndex(), Qt.NoItemSelection)
            except Exception:
                pass
        try:
            view.setCurrentIndex(QModelIndex())
        except Exception:
            pass

    def _on_removed_children(self, *args) -> None:
        if common.LOG:
            common.log_calls(common.logFile, f"OpenedProjects._on_removed_children(args={args!r})")
        nodes = None
        for arg in args:
            if isinstance(arg, list):
                nodes = arg
                break
        if nodes is None:
            self._prune_removed_groups()
            return
        for node in nodes:
            is_group = getattr(node, "isGroup", None)
            if callable(is_group) and is_group():
                self.remove_by_group(node)

    def _prune_removed_groups(self) -> None:
        if common.LOG:
            common.log_calls(common.logFile, "OpenedProjects._prune_removed_groups()")
        try:
            root = QgsProject.instance().layerTreeRoot()
        except Exception:
            return
        if root is None:
            return
        remaining: List[ProjectInfo] = []
        removed = False
        for project in self.projects:
            if project.group is None:
                remaining.append(project)
                continue
            try:
                group_exists = root.findGroup(project.folder_name)
            except Exception:
                group_exists = None
            if group_exists is not None:
                remaining.append(project)
            else:
                removed = True
        self.projects = remaining
        if removed:
            self._handle_project_removed()
