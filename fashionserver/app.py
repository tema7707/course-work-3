import sys

sys.path.append('..')
sys.path.append('.')

import io
import numpy as np
import cv2
import torch
import base64
from io import BytesIO
import PIL

from models.viton import Viton, make_image
from models.keypoint import KeyPointPredictor
from models.segmentation import Segmentator
from models.posenet import DensePosePredictor
from models.segmentation import Segmentator
from network_utils.network_utils import CPDataset
from utils.utils import convert_image
from torchvision import transforms

from flask import Flask, jsonify, request
from scipy.ndimage.filters import gaussian_filter
from PIL import Image

app = Flask(__name__)

transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])

transform_1d = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.5,), (0.5,))])


def pipeline(img, cloth, cloth_mask):
    img_array = np.array(img)
    img_array = convert_image(img)
    img = Image.fromarray(convert_image(np.array(img)))
    img = transform(img)
    im_255 = cv2.resize(img_array, (255, 255), interpolation = cv2.INTER_AREA)
    dp = DensePosePredictor("./detectron2_repo/projects/DensePose/configs/densepose_rcnn_R_50_FPN_s1x.yaml", 
                            "./checkpoint/densepose_rcnn_R_50_FPN_s1x.pkl")
    phead, body = dp.predict(im_255)
    body = cv2.resize(body, (192, 256), interpolation = cv2.INTER_AREA)
    body = Image.fromarray((body*255).astype(np.uint8))
    body = body.resize((192//16, 256//16), Image.BILINEAR)
    body = body.resize((192, 256), Image.BILINEAR)
    phead = cv2.resize(phead, (192, 256), interpolation = cv2.INTER_AREA)
    phead = torch.from_numpy(phead[np.newaxis,:,:])
    head = img * phead - (1 - phead)
    shape = transform_1d(body).type(torch.float32)

    key_model = KeyPointPredictor()
    pose_map, _ = key_model.predict(img_array)

    pose_map_corect = torch.zeros((18, 256, 192)) - 1 
    pose_map_corect[0] = pose_map[0]
    pose_map_corect[1] = pose_map[17]
    pose_map_corect[2] = pose_map[6]
    pose_map_corect[3] = pose_map[8]
    pose_map_corect[4] = pose_map[10]
    pose_map_corect[5] = pose_map[5]
    pose_map_corect[6] = pose_map[7]
    pose_map_corect[7] = pose_map[9]
    pose_map_corect[8] = pose_map[12]
    pose_map_corect[11] = pose_map[11]
    pose_map_corect[14] = pose_map[2]
    pose_map_corect[15] = pose_map[1]
    pose_map_corect[16] = pose_map[4]
    pose_map_corect[17] = pose_map[3]
    pose_map = torch.tensor(pose_map_corect).type(torch.float32)


    viton = Viton(gmm_checkpoint_path='./checkpoint/gmm_train_new/gmm_final.pth', 
                tom_checkpoint_path='./checkpoint/tom_train_new/tom_final.pth')
    shape = Image.open('./datasets/data/train/cloth/000003_1.jpg') # path to cloth
    shape = transform_1d(shape)
    res = viton.run_viton(head, pose_map, shape, cloth, cloth_mask)

    img_array[np.array(body) == -1] = 0
    cv2.imwrite("body.jpg", img_array)
    cv2.imwrite("body2.jpg", np.array(body))

    return encode((np.array(res[0].cpu().detach()).transpose(1, 2, 0) + 1) * 127.5)


def decode(byte64_str):
    bytes = BytesIO(base64.b64decode(byte64_str))
    pil_img = PIL.Image.open(bytes)
    return pil_img


def encode(img):
    pil_img = Image.fromarray(img.astype('uint8'))
    pil_img = pil_img.convert('RGB')
    buff = BytesIO()
    pil_img.save(buff, format="JPEG")
    return base64.b64encode(buff.getvalue()).decode("utf-8")


@app.route('/style/api/v1.0/segmentate', methods=['POST'])
def predict():
    if request.method == 'POST':
        file = request.values['file']
        cloth_id = int(request.values['cloth'])
        if cloth_id == 0:
            c = Image.open(
                '/home/tema/Projects/Course-work-3/datasets/viton_resize/train/cloth/000736_1.jpg')  # path to cloth
            c = transform(c)
            cm = Image.open(
                '/home/tema/Projects/Course-work-3/datasets/viton_resize/train/cloth-mask/000736_1.jpg')  # path to cloth-mask
            cm_array = np.array(cm)
            cm_array = (cm_array >= 128).astype(np.float32)
            cm = torch.from_numpy(cm_array)
            cm.unsqueeze_(0)

        img = decode(file)
        res = pipeline(img, c, cm)
    return encode(np.array(res[0].cpu().detach()).transpose(1,2,0) * 255)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
