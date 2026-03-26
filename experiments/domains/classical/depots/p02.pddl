(define (problem depots-p02)
  (:domain depots)
  (:objects
    depot0 - depot
    distributor0 - distributor
    truck0 - truck
    hoist0 hoist1 - hoist
    pallet0 pallet1 - pallet
    crate0 crate1 - crate)
  (:init
    (at truck0 distributor0)
    (at hoist0 depot0)
    (available hoist0)
    (at hoist1 distributor0)
    (available hoist1)
    (at pallet0 depot0)
    (clear pallet0)
    (at pallet1 distributor0)
    (at crate0 distributor0)
    (on crate0 pallet1)
    (at crate1 distributor0)
    (on crate1 crate0)
    (clear crate1))
  (:goal (and (on crate0 pallet0) (on crate1 pallet1))))
