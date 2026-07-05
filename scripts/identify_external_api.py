import json
import os
import openai
import argparse
import dotenv
from api_analyze import analyze_a_project, classify_api_of_a_project, safe_save_json
from utils.llm_call import get_gemini_client, get_openai_client



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects", type=str, required=True)
    parser.add_argument("--output_file", type=str, default="")
    args = parser.parse_args()
    
    
    
    with open(args.projects, "r") as f:
        projects = json.load(f)
    
    if args.output_file == "":
        args.output_file = "call_graph_labeled.json"

    client1 = get_openai_client()
    client2 = get_gemini_client()
    # index = 40
    for project in projects:
        print(f"-----------------------{project}--------------------------")
        print(f"project path: {os.path.join('results', project)}")
        if projects[project]['analysis_result'] != 'success':
            continue
        
        project_path = os.path.join("results", project)
        output_file = os.path.join(project_path, args.output_file)
        
        # TODO: temporarily force rerun 
        # call_graph = analyze_a_project(project, client1, client2, force_rerun=False, cache_path="tool_analyzer/api_cache.json", output_file=args.output_file)
        call_graph = analyze_a_project(project, client1, client2, force_rerun=True, cache_path="tool_analyzer/api_cache.json", output_file=args.output_file)
        
        if call_graph == {}:
            continue
        safe_save_json(call_graph, output_file)
        
        call_graph = classify_api_of_a_project(project, client1, cache_path="tool_analyzer/api_cache.json", output_file=args.output_file)
        # index -= 1
        # if index == 0:
        #     break
        
        
    
        
        

            



        
        