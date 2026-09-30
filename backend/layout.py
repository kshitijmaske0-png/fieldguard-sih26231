"""Reference-card geometry shared by the card generator and the vision pipeline.

Physical card: A5 landscape, 210 x 148 mm. Four ArUco markers (DICT_4X4_50, ids 0..3 =
TL, TR, BR, BL) are 22 mm squares whose CENTRES sit 14 mm in from each card edge.
The vision pipeline warps the photo so those four marker centres land on the corners
of a CARD_W x CARD_H image, so every position below is stored in millimetres from the
card corner and converted with mm_to_px().
"""
CARD_MM = (210.0, 148.0)
MARKER_MM = 22.0
MARKER_INSET_MM = 14.0                     # marker centre distance from card edge
PX_PER_MM = 5.0
CARD_W = int(round((CARD_MM[0] - 2 * MARKER_INSET_MM) * PX_PER_MM))   # 910
CARD_H = int(round((CARD_MM[1] - 2 * MARKER_INSET_MM) * PX_PER_MM))   # 600
MARKER_CENTRES_MM = {0: (14, 14), 1: (196, 14), 2: (196, 134), 3: (14, 134)}

# name -> (nominal sRGB 0..255, centre x mm, centre y mm). Nominal values are only a
# fallback: replace them with values measured from a photo of the printed card
# (tools/calibrate.py card ...), because printed colours never equal the design RGB.
_ROW1_Y, _ROW2_Y = 42.0, 66.0
_X0, _DX = 41.0, 32.0
PATCHES = {
    "white":      ((255, 255, 255), _X0 + 0 * _DX, _ROW1_Y),
    "light_grey": ((200, 200, 200), _X0 + 1 * _DX, _ROW1_Y),
    "mid_grey":   ((128, 128, 128), _X0 + 2 * _DX, _ROW1_Y),
    "dark_grey":  ((64, 64, 64),    _X0 + 3 * _DX, _ROW1_Y),
    "black":      ((0, 0, 0),       _X0 + 4 * _DX, _ROW1_Y),
    "red":        ((220, 40, 40),   _X0 + 0 * _DX, _ROW2_Y),
    "green":      ((40, 170, 60),   _X0 + 1 * _DX, _ROW2_Y),
    "blue":       ((40, 70, 200),   _X0 + 2 * _DX, _ROW2_Y),
    "yellow":     ((240, 220, 40),  _X0 + 3 * _DX, _ROW2_Y),
    "magenta":    ((210, 50, 160),  _X0 + 4 * _DX, _ROW2_Y),
}
PATCH_SIZE_MM = (28.0, 20.0)
PATCH_READ_R_PX = 20                       # median radius when measuring a patch

SAMPLE_CENTRE_MM = (105.0, 105.0)          # kit tube / pad goes here
SAMPLE_WINDOW_MM = (70.0, 42.0)            # printed outline
SAMPLE_GUIDE_DIAM_MM = 30.0                # printed circle guide
SAMPLE_READ_R_PX = 22


def mm_to_px(x_mm, y_mm):
    return (int(round((x_mm - MARKER_INSET_MM) * PX_PER_MM)),
            int(round((y_mm - MARKER_INSET_MM) * PX_PER_MM)))
