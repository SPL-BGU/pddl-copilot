;; 4 blocks: reverse a tower
(define (problem bw-p02)
  (:domain blocksworld)
  (:objects a b c d)
  (:init
    (on a b) (on b c) (ontable c) (ontable d)
    (clear a) (clear d)
    (handempty))
  (:goal (and (on d c) (on c b) (on b a))))
