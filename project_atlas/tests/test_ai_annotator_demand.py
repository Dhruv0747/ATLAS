"""Exercise inference/structured output and viewer demand without GPU or ROS."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

SOURCE=Path(__file__).resolve().parents[1]/'scripts/ai_annotator_node.py'


class DemandTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse(SOURCE.read_text())
        original=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Annotator')
        cb=next(n for n in original.body if isinstance(n,ast.FunctionDef) and n.name=='cb')
        cls=ast.ClassDef(name='Annotator',bases=[],keywords=[],body=[cb],decorator_list=[])
        self.image=NS(shape=(720,1280,3))
        self.cv=Mock(IMREAD_COLOR=1,COLOR_BGR2RGB=2,IMWRITE_JPEG_QUALITY=3,FONT_HERSHEY_SIMPLEX=4)
        self.cv.imdecode.return_value=self.image
        self.cv.cvtColor.return_value=self.image
        self.cv.imencode.return_value=(True,NS(tobytes=lambda:b'jpeg'))
        self.clock=Mock(return_value=10.)
        scope={'time':NS(time=self.clock),'json':json,'cv2':self.cv,
               'np':NS(frombuffer=lambda *args:b'frame',uint8=1),
               'CompressedImage':lambda:NS(),'String':lambda **kw:NS(**kw),'COCO':['person']}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),str(SOURCE),'exec'),scope)
        self.node=scope['Annotator']()
        self.node.enabled=True;self.node.last=0.
        self.node.det=Mock();self.node.det.infer.return_value=[(1,2,30,40,0,.9)]
        self.node.pub=Mock();self.node.pub.get_subscription_count.return_value=0
        self.node.detection_pub=Mock();self.node.get_logger=Mock(return_value=Mock())
        self.message=NS(header=object(),data=b'rawjpeg')

    def test_no_viewer_keeps_inference_and_structured_detections(self):
        self.node.cb(self.message)
        self.node.det.infer.assert_called_once()
        self.node.detection_pub.publish.assert_called_once()
        payload=json.loads(self.node.detection_pub.publish.call_args.args[0].data)
        self.assertEqual((payload['width'],payload['height']),(1280,720))
        self.assertEqual(payload['detections'][0]['label'],'person')
        self.cv.rectangle.assert_not_called();self.cv.putText.assert_not_called()
        self.cv.imencode.assert_not_called();self.node.pub.publish.assert_not_called()

    def test_viewer_restores_identical_jpeg_header_format_and_quality(self):
        self.node.pub.get_subscription_count.return_value=1
        self.node.cb(self.message)
        self.assertEqual(self.cv.rectangle.call_count,2)
        self.cv.imencode.assert_called_once_with('.jpg',self.image,[3,60])
        image=self.node.pub.publish.call_args.args[0]
        self.assertIs(image.header,self.message.header)
        self.assertEqual((image.format,image.data),('jpeg',b'jpeg'))
        self.node.detection_pub.publish.assert_called_once()

    def test_viewer_comes_and_goes_without_restarting_or_disabling_detection(self):
        for i,viewers in enumerate((0,1,0,1)):
            self.clock.return_value=10.+i
            self.node.pub.get_subscription_count.return_value=viewers
            self.node.cb(self.message)
        self.assertEqual(self.node.det.infer.call_count,4)
        self.assertEqual(self.node.detection_pub.publish.call_count,4)
        self.assertEqual(self.node.pub.publish.call_count,2)

    def test_existing_disabled_and_rate_limit_behavior_preserved(self):
        self.node.enabled=False;self.node.cb(self.message)
        self.node.enabled=True;self.node.last=9.9;self.node.cb(self.message)
        self.node.det.infer.assert_not_called()
        self.node.detection_pub.publish.assert_not_called()

    def test_no_objects_still_publishes_empty_structured_result(self):
        self.node.det.infer.return_value=[]
        self.node.cb(self.message)
        self.assertEqual(json.loads(self.node.detection_pub.publish.call_args.args[0].data)['detections'],[])


if __name__=='__main__':unittest.main()
