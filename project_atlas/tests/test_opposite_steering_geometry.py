import ast
from pathlib import Path


SOURCE = Path(__file__).parents[1] / 'scripts' / 'yahboom_base.py'


def load_geometry():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    names = {
        'FRONT_STEER_CENTER', 'REAR_STEER_CENTER',
        'FRONT_STEER_RIGHT', 'FRONT_STEER_LEFT',
        'REAR_STEER_RIGHT', 'REAR_STEER_LEFT',
    }
    namespace = {}
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in names
            for target in node.targets
        ):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == 'opposite_steering_targets':
            body.append(node)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


def test_positive_turn_uses_opposite_rear_endpoint():
    values = load_geometry()
    front, rear = values['opposite_steering_targets'](1.0)
    assert front == values['FRONT_STEER_RIGHT']
    assert rear == values['REAR_STEER_LEFT']


def test_negative_turn_uses_opposite_rear_endpoint():
    values = load_geometry()
    front, rear = values['opposite_steering_targets'](-1.0)
    assert front == values['FRONT_STEER_LEFT']
    assert rear == values['REAR_STEER_RIGHT']


def test_neutral_returns_both_centres():
    values = load_geometry()
    front, rear = values['opposite_steering_targets'](0.0)
    assert front == values['FRONT_STEER_CENTER']
    assert rear == values['REAR_STEER_CENTER']
