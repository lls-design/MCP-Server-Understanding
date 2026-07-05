import json
import os
import sys
import copy
import shutil

if __name__ == "__main__":
    with open("results/0-results/call_graph_result.json", "r") as f:
        projects = json.load(f)
    
    for project in projects:
        print(f"-----------------------{project}--------------------------")
        print(f"Processing call graph {os.path.join('results', project, 'call_graph.json')}")
        call_graph_path = os.path.join("results", project, "call_graph.json")
        if not os.path.exists(call_graph_path):
            continue
        with open(call_graph_path, "r") as f:
            call_graph = json.load(f)
        
        path_set = {}
        node_label = {}
        node_index = 0
        for node in call_graph:
            path_projet = call_graph[node]['path']
            if path_projet in path_set:
                node_label[int(node)] = path_set[path_projet]
            else:
                node_label[int(node)] = node_index
                path_set[path_projet] = node_index
                node_index += 1

        new_call_graph = {}
        for node_idx in call_graph:
            node = copy.deepcopy(call_graph[node_idx])
            new_index = node_label[int(node_idx)]
            new_call_graph[new_index] = node
            node['successors'] = []
            for successor in call_graph[node_idx]['successors']:
                node['successors'].append(node_label[int(successor)])
            node['successors'] = list(set(node['successors']))
        
        

        with open(os.path.join("results", project, "invoked_functions.json"), "r") as f:
            invoked_functions = json.load(f)
        
        print(f"Processing invoked functions {os.path.join('results', project, 'invoked_functions.json')}")

        new_invoked_functions = {}
        for function in invoked_functions:
            if invoked_functions[function]['entry_index'] == -1:
                continue
            node = copy.deepcopy(invoked_functions[function])
            new_invoked_functions[function] = node
            node['entry_index'] = node_label[node['entry_index']]
            node['visited'] = []
            for visited in invoked_functions[function]['visited']:
                node['visited'].append(node_label[visited])
            node['visited'] = list(set(node['visited']))
            node['leaf_nodes'] = []
            for leaf_node in invoked_functions[function]['leaf_nodes']:
                node['leaf_nodes'].append(node_label[leaf_node])
            node['leaf_nodes'] = list(set(node['leaf_nodes']))
        shutil.copy(os.path.join("results", project, "call_graph.json"), os.path.join("results", project, "call_graph_backup.json"))
       
        
        if not os.path.exists(os.path.join("results", project, "invoked_functions_backup.json")):
            shutil.copy(os.path.join("results", project, "invoked_functions.json"), os.path.join("results", project, "invoked_functions_backup.json"))

        if not os.path.exists(os.path.join("results", project, "call_graph_backup.json")):
            shutil.copy(os.path.join("results", project, "call_graph.json"), os.path.join("results", project, "call_graph_backup.json"))

        with open(os.path.join("results", project, "invoked_functions.json"), "w") as f:
            json.dump(new_invoked_functions, f, indent=4)
        with open(os.path.join("results", project, "call_graph.json"), "w") as f:
            json.dump(new_call_graph, f, indent=4)
        