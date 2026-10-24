#pragma once
// Offline candidate. No cross-call cache; preserve standard executor readiness.
#include <rclcpp/memory_strategy.hpp>
#include <rclcpp/subscription_base.hpp>
#include <utility>
namespace atlas_offline {
using Match=std::pair<rclcpp::SubscriptionBase::SharedPtr,rclcpp::CallbackGroup::SharedPtr>;
inline Match lookup(const std::shared_ptr<const rcl_subscription_t>& handle,
                   const rclcpp::memory_strategy::MemoryStrategy::WeakCallbackGroupsToNodesMap& groups) {
    for(const auto& entry:groups) {
        auto group=entry.first.lock();
        if(!group)continue;
        auto sub=group->find_subscription_ptrs_if([&](const auto& candidate) {
            return candidate->get_subscription_handle()==handle;
        });
        if(sub) {
            // Original second lookup requires a live node too. Do not promote
            // an expired node or retain any ownership between calls.
            if(entry.second.expired())return {sub,nullptr};
            return {sub,group};
        }
    }
    return {};
}
}
