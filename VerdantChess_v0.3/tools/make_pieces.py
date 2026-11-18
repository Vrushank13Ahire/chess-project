"""Renders the piece sprites and writes pieces_data.py (run once; output is shipped with the app).
Vector source: python-chess's bundled piece set (Colin M.L. Burnett, GPL-compatible), re-coloured
with a soft grey-outlined look and a light gradient."""
import base64, io, sys, chess.svg, cairosvg
SIZES = [24, 48, 56, 64, 72, 80, 88, 96, 104]
DEFS = ('<defs>'
 '<linearGradient id="wg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d9d9d9"/></linearGradient>'
 '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6b6b6b"/><stop offset="1" stop-color="#3a3a3a"/></linearGradient>'
 '<filter id="sh" x="-20%" y="-10%" width="140%" height="140%"><feDropShadow dx="0" dy="0.9" stdDeviation="0.7" flood-color="#000" flood-opacity="0.35"/></filter></defs>')

def style(key, g):
    white = key.isupper()
    g = g.replace('stroke="#000"', 'stroke="%s"' % ("#3b3b3b" if white else "#1c1c1c"))
    g = g.replace("stroke:#000000", "stroke:%s" % ("#3b3b3b" if white else "#1c1c1c"))
    g = g.replace("stroke-width=\"1.5\"", "stroke-width=\"1.7\"").replace('stroke="#fff"', 'stroke="#e6e6e6"')
    if white:
        g = g.replace("fill:#ffffff", "fill:url(#wg)").replace('fill="#fff"', 'fill="url(#wg)"')
    else:
        g = g.replace("fill:#000000", "fill:url(#bg)").replace('fill="#000"', 'fill="url(#bg)"')
    return g

def svg_for(key, size):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45" width="%d" height="%d">%s'
            '<g filter="url(#sh)" transform="translate(22.5 22.5) scale(1.06) translate(-22.5 -22.5)">%s</g></svg>'
            % (size, size, DEFS, style(key, chess.svg.PIECES[key])))

if __name__ == "__main__":
    out = {}
    for s in SIZES:
        out[s] = {}
        for key in "PNBRQKpnbrqk":
            name = ("w" if key.isupper() else "b") + key.upper()
            png = cairosvg.svg2png(bytestring=svg_for(key, s).encode(), output_width=s, output_height=s)
            out[s][name] = base64.b64encode(png).decode()
    with open(sys.argv[1] if len(sys.argv) > 1 else "pieces_data.py", "w") as f:
        f.write('"""Auto-generated piece sprites (see make_pieces.py)."""\nSPRITES = {\n')
        for s, d in out.items():
            f.write("  %d: {\n" % s)
            for k, v in d.items():
                f.write('    "%s": "%s",\n' % (k, v))
            f.write("  },\n")
        f.write("}\n")
