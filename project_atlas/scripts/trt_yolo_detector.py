#!/usr/bin/env python3
"""Small TensorRT 10 YOLOv8 detector for Jetson, without PyTorch/PyCUDA."""
import ctypes
import math

import cv2
import numpy as np
import tensorrt as trt


class TensorRTYOLO:
    def __init__(self, engine_path, confidence=0.45, iou=0.45):
        self.confidence = confidence
        self.iou = iou
        self.log = trt.Logger(trt.Logger.WARNING)
        with open(engine_path, "rb") as handle:
            self.engine = trt.Runtime(self.log).deserialize_cuda_engine(handle.read())
        if self.engine is None:
            raise RuntimeError("TensorRT could not deserialize the engine")
        self.context = self.engine.create_execution_context()
        self.cudart = ctypes.CDLL("libcudart.so")
        self.cudart.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self.cudart.cudaFree.argtypes = [ctypes.c_void_p]
        self.cudart.cudaMemcpy.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int
        ]
        self.names = [
            self.engine.get_tensor_name(i) for i in range(self.engine.num_io_tensors)
        ]
        self.input_name = next(
            n for n in self.names
            if self.engine.get_tensor_mode(n) == trt.TensorIOMode.INPUT
        )
        self.output_name = next(
            n for n in self.names
            if self.engine.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT
        )
        self.input_shape = tuple(self.engine.get_tensor_shape(self.input_name))
        self.output_shape = tuple(self.engine.get_tensor_shape(self.output_name))
        self.input_dtype = np.dtype(trt.nptype(self.engine.get_tensor_dtype(self.input_name)))
        self.output_dtype = np.dtype(trt.nptype(self.engine.get_tensor_dtype(self.output_name)))
        self.host_input = np.empty(self.input_shape, dtype=self.input_dtype)
        self.host_output = np.empty(self.output_shape, dtype=self.output_dtype)
        self.device_input = self._malloc(self.host_input.nbytes)
        self.device_output = self._malloc(self.host_output.nbytes)
        self.context.set_tensor_address(self.input_name, int(self.device_input.value))
        self.context.set_tensor_address(self.output_name, int(self.device_output.value))

    def _check(self, result, operation):
        if result != 0:
            raise RuntimeError(f"{operation} failed with CUDA error {result}")

    def _malloc(self, size):
        pointer = ctypes.c_void_p()
        self._check(self.cudart.cudaMalloc(ctypes.byref(pointer), size), "cudaMalloc")
        return pointer

    def infer(self, rgb):
        height, width = rgb.shape[:2]
        size = int(self.input_shape[-1])
        ratio = min(size / width, size / height)
        resized_w, resized_h = int(width * ratio), int(height * ratio)
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        pad_x, pad_y = (size - resized_w) // 2, (size - resized_h) // 2
        canvas[pad_y:pad_y + resized_h, pad_x:pad_x + resized_w] = cv2.resize(
            rgb, (resized_w, resized_h)
        )
        tensor = canvas.transpose(2, 0, 1)[None].astype(self.input_dtype) / 255.0
        np.copyto(self.host_input, tensor)
        self._check(self.cudart.cudaMemcpy(
            self.device_input,
            ctypes.c_void_p(self.host_input.ctypes.data),
            self.host_input.nbytes, 1
        ), "H2D")
        if not self.context.execute_async_v3(0):
            raise RuntimeError("TensorRT execute_async_v3 failed")
        self._check(self.cudart.cudaMemcpy(
            ctypes.c_void_p(self.host_output.ctypes.data),
            self.device_output,
            self.host_output.nbytes, 2
        ), "D2H")
        prediction = np.squeeze(self.host_output).T
        scores = prediction[:, 4:]
        class_ids = scores.argmax(axis=1)
        confidences = scores[np.arange(len(scores)), class_ids]
        keep = confidences >= self.confidence
        boxes_raw = prediction[keep, :4]
        confidences = confidences[keep]
        class_ids = class_ids[keep]
        boxes = []
        for cx, cy, bw, bh in boxes_raw:
            x = (float(cx) - float(bw) / 2 - pad_x) / ratio
            y = (float(cy) - float(bh) / 2 - pad_y) / ratio
            boxes.append([int(x), int(y), int(float(bw) / ratio), int(float(bh) / ratio)])
        results = []
        # Suppress duplicate boxes within each class, not across classes. An
        # unusual view can reasonably be both "vase" and "potted plant"; the
        # dashboard should show both hypotheses instead of hiding one.
        for class_id in np.unique(class_ids):
            members = np.where(class_ids == class_id)[0]
            class_boxes = [boxes[int(index)] for index in members]
            class_scores = [float(confidences[int(index)]) for index in members]
            kept = cv2.dnn.NMSBoxes(
                class_boxes, class_scores, self.confidence, self.iou
            )
            for local_index in np.array(kept).reshape(-1) if len(kept) else []:
                index = int(members[int(local_index)])
                x, y, bw, bh = boxes[index]
                results.append((
                    max(0, x), max(0, y), min(width - 1, x + bw), min(height - 1, y + bh),
                    int(class_ids[index]), float(confidences[index])
                ))
        return results

    def close(self):
        for pointer in (getattr(self, "device_input", None), getattr(self, "device_output", None)):
            if pointer:
                self.cudart.cudaFree(pointer)
