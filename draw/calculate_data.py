import os
import sys
import json
import dotenv
import subprocess
from collections import defaultdict, Counter
from utils.dray_figure_frequency import draw_frequency_chart

# Add the project root to the Python path.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codeql_analyzer.codeql_executor import detect_project_type

dotenv.load_dotenv()

codeql_path = os.getenv("CODEQL_PATH")

def count_lines_of_code(directory):
    """Count lines of code in a directory."""
    total_lines = 0
    file_count = 0
    file_types = Counter()
    
    # Common code file extensions.
    code_extensions = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.hpp',
        '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.clj',
        '.hs', '.ml', '.fs', '.dart', '.lua', '.sh', '.bash', '.zsh', '.fish',
        '.sql', '.r', '.m', '.scm', '.el', '.vim', '.lisp', '.prolog', '.ada',
        '.f90', '.f95', '.f03', '.f08', '.pl', '.pm', '.tcl', '.awk', '.sed'
    }
    
    for root, dirs, files in os.walk(directory):
        # Skip common non-code directories.
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', 
                                                'venv', '.venv', 'env', '.env', 'build',
                                                'dist', 'target', 'bin', 'obj', '.vscode',
                                                '.idea', '.history', 'coverage', '.pytest_cache'}]
        
        for file in files:
            file_path = os.path.join(root, file)
            file_ext = os.path.splitext(file)[1].lower()
            
            if file_ext in code_extensions:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = len(f.readlines())
                        total_lines += lines
                        file_count += 1
                        file_types[file_ext] += 1
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    
    return {
        'total_lines': total_lines,
        'file_count': file_count,
        'file_types': dict(file_types)
    }


def analyze_project_statistics():
    """Analyze project statistics."""
    print("Starting project statistics analysis...")
    
    # Load analysis results.
    with open("results/0-results/call_graph_result.json", "r") as f:
        call_graph_result = json.load(f)
    
    # Statistics variables.
    total_projects = len(call_graph_result)
    success_projects = 0
    failed_projects = 0
    project_types = Counter()
    categories = Counter()
    star_ranges = defaultdict(int)
    code_stats = []
    privilege_stats = []
    entry_points_stats = []
    max_code_project = {
        'name': '',
        'total_lines': 0
    }
    max_privilege_project = {
        'name': '',
        'privilege_count': 0
    }

    max_entry_points_project = {
        'name': '',
        'entry_points_count': 0
    }
    
    print(f"Total projects: {total_projects}")
    
    for name, project in call_graph_result.items():
        # Count analysis results.
        if project["analysis_result"] == "success":
            success_projects += 1
        else:
            failed_projects += 1
            continue
        
        # Analyze code statistics for successful projects.
        project_dir = os.path.join('Servers', name)
        if not os.path.exists(project_dir):
            print("!!!! project directory not found: ", project_dir)
            continue
        res = {}
        try:
            # Detect project type.
            project_type = detect_project_type(project_dir)
            project_types[project_type] += 1
            
            # Count lines of code.
            code_info = count_lines_of_code(project_dir)
            
            # code_stats.append()
            res.update({
                'name': name,
                'project_name': project['name'],
                'stars': project['stars'],
                'category': project['category'],
                'project_type': project_type,
                'total_lines': code_info['total_lines'],
                'file_count': code_info['file_count'],
                'file_types': code_info['file_types'],
            })
            code_stats.append(res)

            
            print(f"✓ {name}: {code_info['total_lines']} lines, {code_info['file_count']} files")

            if code_info['total_lines'] > max_code_project['total_lines']:
                max_code_project['name'] = name
                max_code_project['total_lines'] = code_info['total_lines']
            
        except Exception as e:
            print(f"✗ Error analyzing {name}: {e}")
            
        
        result_path = os.path.join('results', name)
        if os.path.exists(result_path) and os.path.exists(os.path.join(result_path, 'call_graph_labeled.json')):
            with open(os.path.join(result_path, 'call_graph_labeled.json'), 'r') as f:
                call_graph_result = json.load(f)
            count = 0
            for node in call_graph_result:
                if 'external_api' in call_graph_result[node] and call_graph_result[node]['external_api']:
                    count += 1
            privilege_stats.append(count)
            res["privilege_count"] = count
            if count > max_privilege_project['privilege_count']:
                max_privilege_project['name'] = name
                max_privilege_project['privilege_count'] = count
        else:
            print("!!!! call graph labeled file not found: ", result_path)

        if os.path.exists(os.path.join(result_path, 'entry_points.json')):
            with open(os.path.join(result_path, 'entry_points.json'), 'r') as f:
                entry_points = json.load(f)
            entry_points_stats.append(len(entry_points))
            res["entry_points_count"] = len(entry_points)
            if len(entry_points) > max_entry_points_project['entry_points_count']:
                max_entry_points_project['name'] = name
                max_entry_points_project['entry_points_count'] = len(entry_points)
        
        
    print(f"max_code_project: {max_code_project}")
    print(f"max_privilege_project: {max_privilege_project}")
    print(f"max_entry_points_project: {max_entry_points_project}")
    
            
    # Generate statistics report.
    stats_report = {
        'summary': {
            'success_projects': success_projects,
        },
        'project_types': dict(project_types),
        "loc_number": [stat['total_lines'] for stat in code_stats],
        'privilege_statistics': privilege_stats,
        'max_code_project': max_code_project,
        'max_privilege_project': max_privilege_project,
        'code_statistics': code_stats,
        'entry_points_statistics': entry_points_stats
    }
    
    # Compute summary statistics for code metrics.
    if code_stats:
        total_lines = sum(stat['total_lines'] for stat in code_stats)
        total_files = sum(stat['file_count'] for stat in code_stats)
        avg_lines = total_lines / len(code_stats)
        avg_files = total_files / len(code_stats)
        avg_privilege_count = 1.0 * sum(privilege_stats) / len(code_stats)
        avg_privilege_per_tool = 1.0 * sum(privilege_stats) / sum(entry_points_stats)

        stats_report['code_summary'] = {
            'total_lines_of_code': total_lines,
            'total_files': total_files,
            'average_lines_per_project': avg_lines,
            'average_files_per_project': avg_files,
            'average_privilege_count_per_project': avg_privilege_count,
        }
    
    
    # Save statistics results.
    with open("results/0-results/project_statistics.json", "w", encoding="utf-8") as f:
        json.dump(stats_report, f, indent=2, ensure_ascii=False)
    
    # Print summary.
    print("\n=== Project Statistics Summary ===")
    print(f"Total projects: {total_projects}")
    print(f"Successful projects: {success_projects}")
    avg_entry_per_server = 1.0 * sum(entry_points_stats) / len(code_stats)
    
    if code_stats:
        print(f"\n=== Code Statistics Summary ===")
        print(f"Total lines of code: {stats_report['code_summary']['total_lines_of_code']:,}")
        print(f"Total files: {stats_report['code_summary']['total_files']:,}")
        print(f"Average lines per project: {stats_report['code_summary']['average_lines_per_project']:.0f}")
        print(f"Average files per project: {stats_report['code_summary']['average_files_per_project']:.0f}")
        print(f"Average sensitive API calls per project: {stats_report['code_summary']['average_privilege_count_per_project']:.2f}")
        print(f"Average sensitive API calls per MCP tool: {avg_privilege_per_tool:.2f}")
        print(f"Average MCP tools per server: {avg_entry_per_server:.2f}")
    
    print(f"\n=== Project Type Distribution ===")
    for project_type, count in project_types.most_common():
        print(f"{project_type}: {count}")
    
    return stats_report

if __name__ == "__main__":
    stats_report = analyze_project_statistics()
    import statistics

    # Print max, min, and median of privilege_statistics.
    privilege_stats = stats_report['privilege_statistics']
    if privilege_stats:
        max_priv = max(privilege_stats)
        min_priv = min(privilege_stats)
        median_priv = statistics.median(privilege_stats)
        print(f"Privilege Statistics - Max: {max_priv}, Min: {min_priv}, Median: {median_priv}, len: {len(privilege_stats)}")
    else:
        print("Privilege Statistics is empty.")

    # Print max, min, and median of code_statistics using total_lines.
    code_stats = stats_report['code_statistics']
    if code_stats:
        lines_list = [stat['total_lines'] for stat in code_stats if 'total_lines' in stat]
        if lines_list:
            max_lines = max(lines_list)
            min_lines = min(lines_list)
            median_lines = statistics.median(lines_list)
            print(f"Code Statistics (total_lines) - Max: {max_lines}, Min: {min_lines}, Median: {median_lines}, len: {len(lines_list)}")
        else:
            print("No total_lines data in code_statistics.")
    else:
        print("Code Statistics is empty.")

    

    divide = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 10000000]
    divide_line = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 1000000]
    divide_entry = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 35, 40, 45, 50, 10000]
    cnt_privilege = [0] * len(divide)
    cnt_code = [0] * len(divide_line)
    cnt_entry = [0] * len(divide_entry)
    for privilege in stats_report['privilege_statistics']:
        for i in range(len(divide)):
            if privilege < divide[i]:
                cnt_privilege[i] += 1
                break
    for code in stats_report['loc_number']:
        for i in range(len(divide_line)):
            if code < divide_line[i]:
                cnt_code[i] += 1
                break
    
    for entry in stats_report['entry_points_statistics']:
        for i in range(len(divide_entry)):
            if entry < divide_entry[i]:
                cnt_entry[i] += 1
                break
    

    entry_points_stats = stats_report['entry_points_statistics']
    if entry_points_stats:
        max_entry_points = max(entry_points_stats)
        min_entry_points = min(entry_points_stats)
        median_entry_points = statistics.median(entry_points_stats)
        print(f"Entry Points Statistics - Max: {max_entry_points}, Min: {min_entry_points}, Median: {median_entry_points}, len: {len(entry_points_stats)}")
    else:
        print("Entry Points Statistics is empty.")
    
    draw_frequency_chart(cnt_privilege, divide, "Sensitive API Call Count", "#7DAEE0")
    draw_frequency_chart(cnt_code, divide_line, "Lines of Code", "#F9AD6A")
    draw_frequency_chart(cnt_entry, divide_entry, "MCP Server Integrated Tool Count", "#96C37D")

    
    
