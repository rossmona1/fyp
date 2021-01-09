import os
import numpy as np
import cv2
import scipy.io as sio
import utils
import random
import dlib

def split_samples(samples_file, train_file, test_file, ratio=0.8):
    with open(samples_file) as samples_fp:
        lines = samples_fp.readlines()
        random.shuffle(lines)

        train_num = int(len(lines) * ratio)
        test_num = len(lines) - train_num
        count = 0
        data = []
        for line in lines:
            count += 1
            data.append(line)
            if count == train_num:
                with open(train_file, "w+") as train_fp:
                    for d in data:
                        train_fp.write(d)
                data = []

            if count == train_num + test_num:
                with open(test_file, "w+") as test_fp:
                    for d in data:
                        test_fp.write(d)
                data = []
    return train_num, test_num

def get_list_from_filenames(file_path):
    with open(file_path) as f:
        lines = f.read().splitlines()
    return lines


class Biwi:
    def __init__(self, data_dir, data_file, batch_size=64, input_size=64, ratio=0.8):
        self.data_dir = data_dir
        self.data_file = data_file
        self.batch_size = batch_size
        self.input_size = input_size
        self.train_file = None
        self.test_file = None
        self.__gen_filename_list(self.data_dir + self.data_file)
        self.train_num, self.test_num = self.__gen_train_test_file(os.path.join(self.data_dir, 'train.txt'), os.path.join(self.data_dir, 'test.txt'), ratio=ratio)

    def __get_input_img(self, file_name):
        detector = dlib.get_frontal_face_detector()
        img_ext = ".png"
        img_path = file_name + '_rgb' + img_ext
        img = cv2.imread(img_path)

        faces = detector(img)

        crop_img = img[100:200, 100:200]
        for face in faces:
            x1 = face.left()
            y1 = face.top()
            x2 = face.right()
            y2 = face.bottom()
            crop_img = img[y1:y2, x1:x2]

        crop_img = cv2.resize(src=crop_img, dsize=(self.input_size, self.input_size))

        crop_img = np.asarray(crop_img)
        normed_img = (crop_img - crop_img.mean())/crop_img.std()

        return normed_img


    def __get_input_label(self, data_dir, file_name, annot_ext='.txt'):
        # Load pose in degrees
        pose_path = os.path.join(data_dir, file_name + '_pose' + annot_ext)
        pose_annot = open(pose_path, 'r')
        R = []
        for line in pose_annot:
            line = line.strip('\n').split(' ')
            l = []
            if line[0] != '':
                for nb in line:
                    if nb == '':
                        continue
                    l.append(float(nb))
                R.append(l)

        R = np.array(R)
        T = R[3, :]
        R = R[:3, :]
        pose_annot.close()

        R = np.transpose(R)

        roll = -np.arctan2(R[1][0], R[0][0]) * 180 / np.pi
        yaw = -np.arctan2(-R[2][0], np.sqrt(R[2][1] ** 2 + R[2][2] ** 2)) * 180 / np.pi
        pitch = np.arctan2(R[2][1], R[2][2]) * 180 / np.pi

        # Bin values
        bins = np.array(range(-99, 99, 3))
        binned_labels = np.digitize([yaw, pitch, roll], bins) - 1

        cont_labels = [yaw, pitch, roll]

        return binned_labels, cont_labels

    def __gen_filename_list(self, filename_list_file):
        if not os.path.exists(filename_list_file):
            with open(filename_list_file, 'w+') as tlf:
                for root, dirs, files in os.walk(self.data_dir):
                    for subdir in dirs:
                        subfiles = os.listdir(os.path.join(self.data_dir, subdir))

                        for f in subfiles:
                            if os.path.splitext(f)[1] == '.png':
                                token = os.path.splitext(f)[0].split('_')
                                filename = token[0] + '_' + token[1]
                                # print(filename)
                                tlf.write(subdir + '/' + filename + '\n')

    def __gen_train_test_file(self, train_file, test_file, ratio=0.8):
        self.train_file = train_file
        self.test_file = test_file
        return split_samples(self.data_dir + self.data_file, self.train_file, self.test_file, ratio=ratio)

    def train_num(self):
        return self.train_num

    def test_num(self):
        return self.test_num

    def save_test(self, name, save_dir, prediction):
        img_path = os.path.join(self.data_dir, name + '_rgb.png')
        # print(img_path)

        cv2_img = cv2.imread(img_path)
        cv2_img = utils.draw_axis(cv2_img, prediction[0], prediction[1], prediction[2], tdx=200, tdy=200,size=100)
        save_path = os.path.join(save_dir, name.split('/')[1] + '.png')
        # print(save_path)
        cv2.imwrite(save_path, cv2_img)

    def data_generator(self, shuffle=True, test=False):
        sample_file = self.train_file
        if test:
            sample_file = self.test_file

        filenames = get_list_from_filenames(sample_file)
        file_num = len(filenames)

        while True:

            if shuffle and not test:
                idx = np.random.permutation(range(file_num))
                filenames = np.array(filenames)[idx]

            max_num = file_num - (file_num % self.batch_size)

            for i in range(start=0, stop=max_num, step=self.batch_size):
                batch_x = []
                batch_yaw = []
                batch_pitch = []
                batch_roll = []
                names = []

                for j in range(self.batch_size):
                    img = self.__get_input_img(filenames[i + j])
                    bin_labels, cont_labels = self.__get_input_label(self.data_dir, filenames[i + j])
                    batch_x.append(img)
                    batch_yaw.append([bin_labels[0], cont_labels[0]])
                    batch_pitch.append([bin_labels[1], cont_labels[1]])
                    batch_roll.append([bin_labels[2], cont_labels[2]])
                    names.append(filenames[i + j])

                batch_x = np.array(batch_x, dtype=np.float32)
                batch_yaw = np.array(batch_yaw)
                batch_pitch = np.array(batch_pitch)
                batch_roll = np.array(batch_roll)

                if test:
                    yield (batch_x, [batch_yaw, batch_pitch, batch_roll], names)
                else:
                    yield (batch_x, [batch_yaw, batch_pitch, batch_roll])
            if test:
                break