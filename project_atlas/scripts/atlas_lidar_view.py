"""Read-only scan projection. Unknown/no-return is never reported as clear."""
import math
import statistics


def project(scan, transform):
    if not all(math.isfinite(v) for v in (transform.translation.x, transform.translation.y,
                                         scan.angle_min, scan.angle_increment)):
        raise ValueError('nonfinite scan geometry or TF translation')
    q = transform.rotation
    norm = math.sqrt(q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w)
    if not math.isfinite(norm) or norm < 1e-9:
        raise ValueError('invalid TF quaternion')
    x, y, z, w = q.x/norm, q.y/norm, q.z/norm, q.w/norm
    a, b, c, d = 1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*y+z*w), 1-2*(x*x+z*z)
    points, closest = [], dict(front=None, left=None, rear=None, right=None)
    members = {key: [] for key in closest}
    minima = dict.fromkeys(closest)
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
            minima[sector] = dict(index=i, raw_range_m=r, raw_angle_rad=angle,
                                 x_m=px, y_m=py, distance_m=distance,
                                 bearing_rad=bearing,
                                 ray_offset_s=i*getattr(scan, 'time_increment', 0.0))
        members[sector].append((i, px, py, distance, bearing))
        points.append([round(px, 4), round(py, 4)])
    surfaces = {}
    for sector, rows in members.items():
        # Diagnostic only. Never replace nearest returns with this estimate.
        # Split at missing rays or >15 cm endpoint gaps; require angular extent.
        groups = []
        for row in rows:
            if (not groups or row[0] != groups[-1][-1][0]+1 or
                    math.hypot(row[1]-groups[-1][-1][1], row[2]-groups[-1][-1][2]) > .15):
                groups.append([])
            groups[-1].append(row)
        if (len(groups) > 1 and groups[0][0][0] == 0 and
                groups[-1][-1][0] == len(scan.ranges)-1 and
                abs(abs(scan.angle_increment)*len(scan.ranges)-2*math.pi) < .05 and
                math.hypot(groups[0][0][1]-groups[-1][-1][1], groups[0][0][2]-groups[-1][-1][2]) <= .15):
            groups[0] = groups[-1]+groups[0]
            groups.pop()
        candidates = [g for g in groups if len(g) >= 5 and
                      (len(g)-1)*abs(scan.angle_increment) >= math.radians(5)]
        group = max(candidates, key=len) if candidates else None
        surfaces[sector] = (dict(distance_m=statistics.median(r[3] for r in group),
                                count=len(group), sector_count=len(rows),
                                angular_span_deg=math.degrees((len(group)-1)*abs(scan.angle_increment)),
                                method='largest contiguous cluster median radial range; not wall clearance')
                            if group else None)
    return dict(points=points, closest=closest, minima=minima, surfaces=surfaces,
                valid=len(points), invalid=len(scan.ranges)-len(points), total=len(scan.ranges),
                sector_definition='90-degree quadrants, front centred on +X; ranges from base_link')
