import matplotlib.pyplot as plt
from collections import Counter
import matplotlib
import numpy as np
from matplotlib import font_manager

# Add a CJK font.
try:
    font = font_manager.FontProperties(fname='/usr/share/fonts/Fangsong.ttf')

    # print(f"Set global font to: {font_name}")
except Exception as e:
    print(f"Failed to load Noto Sans CJK font: {e}")
    # Fall back to other CJK fonts.
    matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
    matplotlib.rcParams['axes.unicode_minus'] = False


def draw_frequency_chart(data, divide, title, color):
    """
    Draw a frequency chart where the x-axis is the value and the y-axis is the
    number of occurrences.
    
    Args:
        data: Numeric list containing all values to count.
        title: Chart title.
    """
    
    # Get values and their corresponding frequencies.

    values = [i for i in range(len(divide))]
    # Increase x/y label font size.
    label_fontsize = 16
    plt.figure(figsize=(10, 6))

    
    plt.gca().tick_params(axis='y', labelsize=label_fontsize)
    # Add headroom on the y-axis so the highest bar does not touch the top.
    if data:
        ymax = max(data)
        plt.ylim(0, ymax * 1.15 if ymax > 0 else 1)
    plt.yticks(fontsize=label_fontsize)
    # Set the spacing between bars to 0.
    plt.bar(values, data, color=color, width=1.0, align='center', edgecolor='black', linewidth=0.5)
    # plt.bar(values, data, color=color)
    plt.title(title, fontproperties=font)
    plt.gca().title.set_fontsize(label_fontsize+2)
    plt.xlabel("Range", fontsize=label_fontsize+2, fontproperties=font)
    div_str = []
    for idx,div in enumerate(divide):
        if idx == len(divide) - 1:
            div_str.append(str(divide[-2]) + "+")
        elif idx == 0 or divide[idx] - divide[idx-1] == 1:
            div_str.append(str(div))
        else:
            str1 = str(div)
            # if div >= 1000:
            #     str1 = f"$10^{{{int(np.log10(div))}}}$"

            div_str.append("<" + str1)
    plt.xticks([v for v in values], div_str, fontsize=label_fontsize-1, rotation=30)
    plt.ylabel("Frequency", fontsize=label_fontsize+2, fontproperties=font)
    # Annotate each bar with its count.
    for idx, count in enumerate(data):
        plt.text(idx, count + max(data)*0.01, str(count), ha='center', va='bottom', fontsize=label_fontsize)

    # plt.grid(True, alpha=0.3)
    
    # Save the image.
    plt.savefig(f"./figures/{title}.png", dpi=300, bbox_inches='tight')
    plt.close()

    


# Usage example.
if __name__ == "__main__":
    # Example data: a numeric list.
    sample_data = [1, 2, 2, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 5]
    
    # Set x-axis ticks.
    divide = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    
    # Draw a frequency chart.
    draw_frequency_chart(sample_data, divide, "Frequency Distribution", "skyblue")
    print("Frequency chart saved as 'Frequency Distribution.png'")
