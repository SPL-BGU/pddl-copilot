;; 5 blocks: rearrange two towers
(define (problem bw-p05)
  (:domain blocksworld)
  (:objects a b c d e)
  (:init
    (on a b) (on b c) (ontable c)
    (on d e) (ontable e)
    (clear a) (clear d)
    (handempty))
  (:goal (and (on e d) (on d c) (on c b) (on b a))))
