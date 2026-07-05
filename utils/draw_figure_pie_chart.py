from matplotlib import font_manager
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
# matplotlib.rcParams['axes.unicode_minus'] = False
font = font_manager.FontProperties(fname='/usr/share/fonts/Fangsong.ttf')

def draw_pie_chart(data, title, colors=None):
    plt.figure(figsize=(10, 10))
    # Set font sizes for pie chart
    # Set font size directly in textprops for pie chart labels and in title, instead of using plt.rcParams
    font_size = 23
    plt.rcParams.update({'font.size': font_size})
    # To set Chinese font for pie chart labels, use the 'fontproperties' parameter
    def make_autopct(values):
        def my_autopct(pct):
            total = sum(values)
            val = int(round(pct * total / 100.0))
            return f'{val} ({pct:.1f}%)'
        return my_autopct

    plt.pie(
        data.values(),
        labels=data.keys(),
        autopct=make_autopct(list(data.values())),
        colors=colors,
        textprops={'fontproperties': font, 'fontsize': font_size}
    )
    plt.title(title, fontproperties=font, fontsize=font_size)
    plt.tight_layout()
    plt.show()
    plt.savefig(f"./figures/{title}.png", dpi=300, bbox_inches='tight')
    plt.close()

if __name__ == "__main__":
    data = {
        'Python': 10,
        'Java': 20,
        'C++': 30,
    }
    # Define a color array and assign a different color to each segment.
    colors = ['#ff9999', '#66b3ff', '#99ff99']
    draw_pie_chart(data, "Pie Chart", colors)
