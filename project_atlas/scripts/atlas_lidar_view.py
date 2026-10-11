"""Read-only scan projection. Unknown/no-return is never reported as clear."""
import math


def project(scan, transform):
    q = transform.rotation
    norm = math.sqrt(q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w)
    if not math.isfinite(norm) or norm < 1e-9:
        raise ValueError('invalid TF quaternion')
    x, y, z, w = q.x/norm, q.y/norm, q.z/norm, q.w/norm
    a, b, c, d = 1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*y+z*w), 1-2*(x*x+z*z)
    points, closest = [], dict(front=None, left=None, rear=None, right=None)
    for i, r in enumerate(scan.ranges):
        if not math.isfinite(r) or not scan.range_min <= r <= scan.range_max:
            continue
        angle = scan.angle_min + i*scan.angle_increment
        sx, sy = r*math.cos(angle), r*math.sin(angle)
        px, py = a*sx+b*sy+transform.translation.x, c*sx+d*sy+transform.translation.y
        distance, bearing = math.hypot(px, py), math.atan2(py, px)
        sector = ('front', 'left', 'rear', 'right')[int((bearing+math.pi/4)%(2*math.pi)/(math.pi/2))]
        if closest[sector] is None or distance < closest[sector]:
            closest[sector] = distance
        points.append([round(px, 4), round(py, 4)])
    return dict(points=points, closest=closest, valid=len(points), invalid=len(scan.ranges)-len(points), total=len(scan.ranges))
