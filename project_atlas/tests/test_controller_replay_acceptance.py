"""Replay acceptance cannot turn absent output into a false safety pass."""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'tools/diagnostics/collision_probe/action_replay.py'
tree=ast.parse(SOURCE.read_text())
scope={}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='assess'],type_ignores=[]),str(SOURCE),'exec'),scope)
assess=scope['assess']

class Acceptance(unittest.TestCase):
    def test_absent_output_alone_fails(self):
        for name in ('left_blocked','rear_unknown','scan_absent_after_timeout'):
            self.assertFalse(assess({name:dict(messages=0,nonzero=0,last=None)})[name])

    def test_unchanged_zero_needs_all_evidence(self):
        row=dict(messages=0,nonzero=0,last=None,initial_final=(0.,0.),controller_zeros=1,action_status=6)
        self.assertTrue(assess({'left_blocked':row})['left_blocked'])
        for field,value in [('initial_final',(.1,0.)),('controller_zeros',0),('action_status',4)]:
            self.assertFalse(assess({'left_blocked':dict(row,**{field:value})})['left_blocked'])

    def test_tuple_and_json_list_agree(self):
        for zero in ([0.,0.],(0.,0.)):
            self.assertTrue(assess({'rear_unknown':dict(messages=10,nonzero=0,last=zero)})['rear_unknown'])

    def test_unsafe_nonzero_cannot_pass(self):
        self.assertFalse(assess({'rear_unknown':dict(messages=10,nonzero=1,last=(0.,0.))})['rear_unknown'])

if __name__=='__main__':unittest.main()
