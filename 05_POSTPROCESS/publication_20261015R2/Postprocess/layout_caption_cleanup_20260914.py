"""Publication layout and caption separation, without altering plotted data."""

from matplotlib.transforms import Bbox


def _clear_titles(axes):
    for ax in axes:
        for loc in ('left', 'center', 'right'):
            ax.set_title('', loc=loc)


def apply(fig, panels, key):
    if key == 'Fig6':
        _clear_titles(panels)
        fig.set_size_inches(171 / 25.4, 6.3, forward=True)
        for ax, pos in zip(panels, [
            [.15, .68, .35, .245], [.64, .68, .345, .245],
            [.15, .145, .35, .435], [.64, .145, .345, .435],
        ]):
            ax.set_position(pos)
        for t in list(fig.texts):
            if 'Expanded*' in t.get_text():
                t.remove()
        for ax in panels[:2]:
            for t in list(ax.texts):
                if 'area' in t.get_text().lower():
                    t.remove()
        bars = [ax for ax in fig.axes if hasattr(ax, '_colorbar')]
        for ax, label in zip(bars, ['Duration (h)', 'Reference − existing (GW)']):
            ax._colorbar.set_label(label, fontsize=7.2, labelpad=2)
        legend = panels[2].get_legend()
        if legend:
            legend.set_bbox_to_anchor((1, 1.055))
        for ax in panels:
            for t in ax.texts:
                if t.get_text() in ('a', 'b', 'c', 'd'):
                    t.set_position((-.10, 1.045))

    if key == 'Fig7':
        for t in list(fig.texts):
            if 'Ideal additions for fixed 2033' in t.get_text():
                t.remove()
        panels[4].set_position([.15, .087, .81, .193])

    if key in ('FigS02', 'FigS05', 'FigS10', 'FigS11', 'FigS13'):
        _clear_titles(panels)

    if key == 'FigS12':
        for t in list(fig.texts):
            if 'Color is scaled' in t.get_text():
                t.remove()
        fig.set_size_inches(171 / 25.4, 6.65, forward=True)
        for ax, pos in zip(panels, [
            [.16, .58, .32, .30], [.66, .58, .30, .30],
            [.16, .12, .32, .28], [.66, .12, .30, .28],
        ]):
            ax.set_position(pos)

    if key == 'FigS13':
        for t in list(fig.texts):
            if 'Fixed portfolios' in t.get_text():
                t.remove()
        fig.set_size_inches(171 / 25.4, 6.7, forward=True)
        for ax, pos in zip(panels, [
            [.16, .58, .32, .30], [.68, .58, .29, .30],
            [.16, .17, .32, .28], [.68, .17, .29, .28],
        ]):
            ax.set_position(pos)
        for ax in fig.axes:
            if hasattr(ax, '_colorbar'):
                ax.set_position([.505, .195, .012, .225])
                ax._colorbar.set_label('GW', fontsize=7.2, labelpad=3)

    if key == 'FigS14':
        for t in list(fig.texts):
            if t.get_text().startswith('Rows 01'):
                t.remove()
        _clear_titles(panels)
        fig.set_size_inches(171 / 25.4, 7.6, forward=True)
        for ax, letter in zip(panels, 'abcd'):
            b = ax.get_position()
            ax.set_position([b.x0, .155, b.width, .705])
            ax.text(0, 1.032, letter, transform=ax.transAxes,
                    fontfamily='Arial', fontweight='bold', fontsize=9)
        panels[2].set_xlabel('Technology', fontsize=7.2)
        panels[3].set_xlabel('Build year', fontsize=7.2)
