"""Generate a private, hash-pinned strategy variant; never edit /opt/ros."""
import hashlib
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(source).hexdigest() == '73504657a39bb47bcf08f2b763d7525d3f11505f54c93b7480b15300f8825e7b', 'unreviewed ROS header'
text = source.decode()
old = 'auto subscription = get_subscription_by_handle(*it, weak_groups_to_nodes);'
assert text.count(old) == 1
text = text.replace(old, 'auto match = atlas_offline::lookup(*it, weak_groups_to_nodes);\n      auto subscription = match.first;')
old = 'auto group = get_group_by_subscription(subscription, weak_groups_to_nodes);'
assert text.count(old) == 1
text = text.replace(old, 'auto group = match.second;')
text = text.replace('allocator_memory_strategy', 'atlas_onepass_memory_strategy')
text = text.replace('RCLCPP__STRATEGIES__ALLOCATOR_MEMORY_STRATEGY_HPP_', 'ATLAS_OFFLINE_ONEPASS_STRATEGY_HPP_')
Path(sys.argv[2]).write_text('#include "onepass_lookup.hpp"\n' + text)
