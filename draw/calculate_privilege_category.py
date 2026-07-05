import os
import json


with open(os.path.join("results/0-results", "call_graph_result.json"), "r") as f:
    call_graph_result = json.load(f)

category_cnt = [0 for _ in range(8)] 

for project in call_graph_result:
    if call_graph_result[project]["analysis_result"] != "success":
        continue
    
    call_graph_path = os.path.join("results/0-results", project, "call_graph_labeled.json")
    if not os.path.exists(call_graph_path):
        print(f"!!! call graph not found: {call_graph_path}")
        continue
    with open(call_graph_path, "r") as f:
        call_graph = json.load(f)
    for node in call_graph:
        if 'category' in call_graph[node]:
            # print(call_graph[node]['category'])
            category_cnt[int(call_graph[node]['category'])] += 1
    

print(category_cnt)
print(sum(category_cnt))
print([i * 1.0 / sum(category_cnt) for i in category_cnt])