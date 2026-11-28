"""PC-only ROS context semantics, not a camera-driver or hardware acceptance test."""
import os
import platform
import unittest


@unittest.skipUnless(platform.machine()=='x86_64' and os.environ.get('ATLAS_PC_CONTEXT_TEST')=='1',
                     'explicit isolated PC ROS test only')
class ContextSemantics(unittest.TestCase):
    def test_creation_before_shutdown_and_rejection_after(self):
        import rclpy
        from rclpy.context import Context
        from rclpy.node import Node
        from std_msgs.msg import String
        ctx=Context();rclpy.init(context=ctx,domain_id=171)
        node=Node('atlas_offline_context_test',context=ctx,enable_rosout=False,
                  start_parameter_services=False)
        try:
            publisher=node.create_publisher(String,'/isolated_context_test',1)
            self.assertTrue(ctx.ok());self.assertIsNotNone(publisher)
            ctx.shutdown()
            self.assertFalse(ctx.ok())
            with self.assertRaises(Exception):
                node.create_publisher(String,'/isolated_after_shutdown',1)
        finally:
            node.destroy_node()
            if ctx.ok():ctx.shutdown()


if __name__=='__main__':unittest.main()
