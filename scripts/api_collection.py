from cgi import print_form
import os
import json
import logging

logger = logging.getLogger("tool_analyzer")

def bfs_traverse(call_graphs_json: dict, entry_function_index: int) -> dict:

    queue = [entry_function_index]
    visited = set()
    leaf_nodes = set()
    while queue:
        current_index = queue.pop(0)
        visited.add(current_index)
        current_node = call_graphs_json[current_index]
        if len(current_node['successors']) == 0:
            leaf_nodes.add(current_index)
            continue
        for neighbor_index in current_node['successors']:
            if neighbor_index in visited:
                continue
            queue.append(neighbor_index)
            visited.add(neighbor_index)
    return visited, leaf_nodes

def collect_invoked_functions(call_graphs_json: dict, entry_points: dict) -> dict:
    """
    Collect the invoked functions from the call graphs.
    """
    invoked_functions = {}  
    for tool_name, entry_point in entry_points.items():
        entry_index = None
        for node_index, node in call_graphs_json.items():
            if not node['des'].startswith("Source"):
                continue
            file_name = os.path.basename(entry_point['file'])
            # print("!!!! file_name: ", file_name, "node['path']: ", node['path'])
            if file_name in node['path']:
                if tool_name in node['des']:
                    entry_index = node_index
                    break
                lines = node['path'].split(':')
                if int(lines[1]) == entry_point['line_start'] and int(lines[3]) == entry_point['line_end']:
                    entry_index = node_index
                    break
        # print(f"Entry index: {entry_index}")
            
        if entry_index is None:
            logger.error(f"Entry point not found: {entry_point}")
            invoked_functions[tool_name] = {
                "entry_index": -1,
                "visited": [],
                "leaf_nodes": []
            }
            continue
        visited, leaf_nodes = bfs_traverse(call_graphs_json, entry_index)
        invoked_functions[entry_point['tool_name']] = {
            "entry_index": entry_index,
            "visited": list(visited),
            "leaf_nodes": list(leaf_nodes)
        }

    return invoked_functions