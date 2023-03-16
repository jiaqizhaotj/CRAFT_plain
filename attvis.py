import sys

from PIL import Image
import argparse
import os
import numpy as np
import torch

import cv2
torch.set_printoptions(sci_mode=False, precision=4)
np.set_printoptions(suppress=True, precision=4)

def save_matrix(filename, mat, print_stats=False):
    import matplotlib.pyplot as plt
    # corr = F.avg_pool2d(corr, 4, stride=4).squeeze(1).squeeze(0)
    if print_stats:
        print("{}: {}. mean/std: {:.5f}, {:.5f}".format(filename, list(mat.shape), 
               np.abs(mat).mean(), mat.std()))
               
    plt.imshow(mat)
    plt.colorbar()
    plt.savefig(filename) # dpi=1200
    plt.clf()
    print(f"Saved '{filename}'")

def get_boundary(h, w, H, W, radius):
    top = max(0, h - radius)
    bottom = min(H, h + radius + 1)
    left = max(0, w - radius)
    right = min(W, w + radius + 1)
    return top, bottom, left, right

def vis_attention(model_name, img1_path, img2_path, points, attention5d_path, 
                  radius=16, box_radius=8, img_scale=1, alpha=1, savedir='attvis',
                  proj_img2=False):
    img2_name = os.path.basename(img2_path)
    img2_trunk = os.path.splitext(img2_name)[0]
    if img1_path is not None:
        img1_np = cv2.imread(img1_path)
        img1_name = os.path.basename(img1_path)
        img1_trunk = os.path.splitext(img1_name)[0]   
        img1_np = cv2.resize(img1_np, (0,0), fx=img_scale, fy=img_scale)
    else:
        img1_np = None
    img2_np = cv2.imread(img2_path)[:,:,::-1]
    img2_np = cv2.resize(img2_np, (0,0), fx=img_scale, fy=img_scale)
    H, W = img2_np.shape[:2]
    attention5d = torch.load(attention5d_path, map_location='cpu')
    if not os.path.exists(savedir):
        os.makedirs(savedir, exist_ok=True)

    for point in points:
        w0, h0 = point
        w0 = int(w0 * img_scale)
        h0 = int(h0 * img_scale)
        h, w = h0 // 8, w0 // 8
        if img_scale != 1:
            print(f"{point[0]}, {point[1]} => {w0}, {h0} => {w}, {h}")
        else:
            print(f"{w0}, {h0} => {w}, {h}")
        # attention: H//8, W//8
        attention = attention5d[0, h, w].numpy()

        # Set attention outside the radius to 0.
        if radius > 0:
            mask = np.zeros_like(attention, dtype=bool)            
            attn_top, attn_bottom, attn_left, attn_right = get_boundary(h, w, H//8, W//8, radius)
            mask[attn_top:attn_bottom, attn_left:attn_right] = True
            attention = attention * mask.astype(float)
            median = np.median(attention[mask])
        else:
            median = np.median(attention)
            
        neg_count = np.count_nonzero(attention < 0)
        pos_count = np.count_nonzero(attention > 0)
        print(f"{point}: median {median}, {pos_count} > 0, {neg_count} < 0")
        box_top, box_bottom, box_left, box_right = get_boundary(h0, w0, H, W, radius=box_radius)

        if img1_np is not None:
            # draw a square around the point
            # the side length of the square is 2*radius+1
            blank_rect = np.copy(img1_np)
            cv2.rectangle(blank_rect, (box_left, box_top), (box_right, box_bottom), (0, 0, 255), 1)
            img1_np2 = cv2.addWeighted(img1_np, (1-alpha), blank_rect, alpha, 0)
            img1_savename = f"{img1_trunk}-{point[0]},{point[1]}-highlight.png" 
            img1_savepath = os.path.join(savedir, img1_savename)
            cv2.imwrite(img1_savepath, img1_np2)
            print(f"Saved '{img1_savepath}'")

        attention = cv2.resize(attention, (W, H))
        attention -= median
        attention[attention < 0] = 0
        attention = (255 * attention / attention.max()).astype(np.uint8)
        # heatmap: [368, 768, 3]
        heatmap = cv2.applyColorMap(attention, cv2.COLORMAP_JET)[:, :, ::-1]
        overlaid_img2 = img2_np * 0.6 + heatmap * 0.3
        overlaid_img2 = overlaid_img2.astype(np.uint8)

        blank_rect = overlaid_img2.copy()
        # self attention on Frame-2, draw a red rectangle.
        if img1_path == img2_path:
            color = (255, 0, 0)
            cv2.rectangle(blank_rect, (box_left, box_top), (box_right, box_bottom), color, 1)
        # Cross-frame attention. If proj_img2, draw a green rectangle in Frame-2 
        # at the same location of the query in Frame-1.
        elif proj_img2:
            color = (0, 255, 0)
            cv2.rectangle(blank_rect, (box_left, box_top), (box_right, box_bottom), color, 1)

        overlaid_img2 = cv2.addWeighted(overlaid_img2, (1-alpha), blank_rect, alpha, 0)
        overlaid_img2_obj = Image.fromarray(overlaid_img2)
        img2_savename = f"{img2_trunk}-{point[0]},{point[1]}-{model_name}.png"
        img2_savepath = os.path.join(savedir, img2_savename)
        overlaid_img2_obj.save(img2_savepath)
        print(f"Saved '{img2_savepath}'")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', dest="model_name", type=str)
    parser.add_argument('--img1', dest='img1_path', type=str)
    parser.add_argument('--img2', dest='img2_path', type=str)
    # --points is a list of tuples. specified as: --points 11,22.44,77.33,15
    parser.add_argument('--points', type=str)
    parser.add_argument('--att', dest='attention5d_path', type=str, required=True)
    parser.add_argument('--savedir', type=str, default='attvis')
    parser.add_argument('--scale', dest='img_scale', type=float, default=1.0)
    parser.add_argument('--radius', dest='radius', type=int, default=16)
    parser.add_argument('--box_radius', dest='box_radius', type=int, default=8)
    parser.add_argument('--alpha', type=float, default=1)
    parser.add_argument('--proj_img2', action='store_true')

    args = parser.parse_args()

    points = args.points.split(".")
    points = [[int(x) for x in p.split(",")] for p in points]
    vis_attention(args.model_name, args.img1_path, args.img2_path, points, args.attention5d_path, 
                  args.radius, args.box_radius, args.img_scale, args.alpha, args.savedir, args.proj_img2)
