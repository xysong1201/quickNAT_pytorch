import itertools
import os
import re
import shutil
from textwrap import wrap

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import torch
from tensorboardX import SummaryWriter

import evaluator as eu

plt.switch_backend('agg')
plt.axis('scaled')


class LogWriter(object):
    def __init__(self, num_class, log_dir_name, exp_name, use_last_checkpoint=False, labels=None,
                 cm_cmap=plt.cm.Blues):
        self.num_class = num_class
        train_log_path, val_log_path = os.path.join(log_dir_name, exp_name, "train"), os.path.join(log_dir_name,
                                                                                                   exp_name,
                                                                                                   "val")
        if not use_last_checkpoint:
            if os.path.exists(train_log_path):
                shutil.rmtree(train_log_path)
            if os.path.exists(val_log_path):
                shutil.rmtree(val_log_path)

        self.writer = {
            'train': SummaryWriter(train_log_path),
            'val': SummaryWriter(val_log_path)
        }
        self.curr_iter = 1
        self.cm_cmap = cm_cmap
        self.init_cm()
        self.init_ds()
        self.labels = self.beautify_labels(labels)

    def loss_per_iter(self, loss_value, i_batch, current_iteration):
        print('[Iteration : ' + str(i_batch) + '] Loss -> ' + str(loss_value))
        self.writer['train'].add_scalar('loss/per_iteration', loss_value, current_iteration)

    def loss_per_epoch(self, loss_arr, phase, epoch):
        if phase == 'train':
            loss = loss_arr[-1]
        else:
            loss = np.mean(loss_arr)
        self.writer[phase].add_scalar('loss/per_epoch', loss, epoch)
        print('epoch ' + phase + ' loss = ' + str(loss))

    def update_cm_per_iter(self, predictions, correct_labels, phase):
        _, batch_output = torch.max(predictions, dim=1)
        _, cm_batch = eu.dice_confusion_matrix(batch_output, correct_labels, self.num_class)
        self._cm[phase] += cm_batch.cpu()
        del cm_batch, batch_output

    def cm_per_epoch(self, phase, epoch, i_batch):
        print("Confusion Matrix...", end='')
        cm = (self._cm[phase] / (i_batch + 1)).cpu().numpy()
        self.plot_cm('confusion_matrix', phase, cm, epoch)
        self.init_cm()
        print("DONE")

    def plot_cm(self, caption, phase, cm, step=None):
        fig = matplotlib.figure.Figure(figsize=(8, 8), dpi=180, facecolor='w', edgecolor='k')
        ax = fig.add_subplot(1, 1, 1)

        ax.imshow(cm, interpolation='nearest', cmap=self.cm_cmap)
        ax.set_xlabel('Predicted', fontsize=7)
        ax.set_xticks(np.arange(self.num_class))
        c = ax.set_xticklabels(self.labels, fontsize=4, rotation=-90, ha='center')
        ax.xaxis.set_label_position('bottom')
        ax.xaxis.tick_bottom()

        ax.set_ylabel('True Label', fontsize=7)
        ax.set_yticks(np.arange(self.num_class))
        ax.set_yticklabels(self.labels, fontsize=4, va='center')
        ax.yaxis.set_label_position('left')
        ax.yaxis.tick_left()

        thresh = cm.max() / 2.
        for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
            ax.text(j, i, format(cm[i, j], '.2f') if cm[i, j] != 0 else '.', horizontalalignment="center", fontsize=6,
                    verticalalignment='center', color="white" if cm[i, j] > thresh else "black")

        fig.set_tight_layout(True)
        np.set_printoptions(precision=2)
        if step:
            self.writer[phase].add_figure(caption + '/' + phase, fig, step)
        else:
            self.writer[phase].add_figure(caption + '/' + phase, fig)

    def update_dice_score_per_iteration(self, predictions, correct_labels, epoch):
        _, batch_output = torch.max(predictions, dim=1)
        score_vector = eu.dice_score_perclass(batch_output, correct_labels, self.num_class)
        self._ds += score_vector.cpu()

    def dice_score_per_epoch(self, epoch, i_batch):
        print("Dice Score...", end='')
        ds = (self._ds / (i_batch + 1)).cpu().numpy()
        self.plot_dice_score('dice_score_per_epoch', ds, 'Dice Score', epoch)
        self.init_ds()
        print("DONE")

    def plot_dice_score(self, caption, ds, title, step=None):
        fig = matplotlib.figure.Figure(figsize=(8, 6), dpi=180, facecolor='w', edgecolor='k')
        ax = fig.add_subplot(1, 1, 1)
        ax.set_xlabel(title, fontsize=10)
        ax.xaxis.set_label_position('top')
        ax.bar(np.arange(self.num_class), ds)
        ax.set_xticks(np.arange(self.num_class))
        c = ax.set_xticklabels(self.labels, fontsize=6, rotation=-90, ha='center')
        ax.xaxis.tick_bottom()
        if step:
            self.writer['val'].add_figure(caption, fig, step)
        else:
            self.writer['val'].add_figure(caption, fig)

    def plot_eval_box_plot(self, caption, class_dist, title):
        fig = matplotlib.figure.Figure(figsize=(8, 6), dpi=180, facecolor='w', edgecolor='k')
        ax = fig.add_subplot(1, 1, 1)
        ax.set_xlabel(title, fontsize=10)
        ax.xaxis.set_label_position('top')
        ax.boxplot(class_dist)
        ax.set_xticks(np.arange(self.num_class))
        c = ax.set_xticklabels(self.labels, fontsize=6, rotation=-90, ha='center')
        ax.xaxis.tick_bottom()
        self.writer['val'].add_figure(caption, fig)

    def image_per_epoch(self, prediction, ground_truth, phase, epoch):
        print("Sample Images...", end='')
        ncols = 2
        nrows = len(prediction)
        fig, ax = plt.subplots(nrows=nrows, ncols=ncols, figsize=(10, 20))

        for i in range(nrows):
            ax[i][0].imshow(prediction[i], cmap='CMRmap', vmin=0, vmax=self.num_class - 1)
            ax[i][0].set_title("Predicted", fontsize=10, color="blue")
            ax[i][0].axis('off')
            ax[i][1].imshow(ground_truth[i], cmap='CMRmap', vmin=0, vmax=self.num_class - 1)
            ax[i][1].set_title("Ground Truth", fontsize=10, color="blue")
            ax[i][1].axis('off')
        fig.set_tight_layout(True)
        self.writer[phase].add_figure('sample_prediction/' + phase, fig, epoch)
        print('DONE')

    def graph(self, model, X):
        self.writer['train'].add_graph(model, X)

    def close(self):
        self.writer['train'].close()
        self.writer['val'].close()

    def init_cm(self):
        self._cm = {
            'train': torch.zeros(self.num_class, self.num_class),
            'val': torch.zeros(self.num_class, self.num_class)
        }

    def init_ds(self):
        self._ds = torch.zeros(self.num_class)

    def beautify_labels(self, labels):
        classes = [re.sub(r'([a-z](?=[A-Z])|[A-Z](?=[A-Z][a-z]))', r'\1 ', x) for x in labels]
        classes = ['\n'.join(wrap(l, 40)) for l in classes]
        return classes
