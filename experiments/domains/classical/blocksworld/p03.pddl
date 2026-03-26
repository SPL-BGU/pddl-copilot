;; 4 blocks: two towers to one
(define (problem bw-p03)
  (:domain blocksworld)
  (:objects a b c d)
  (:init
    (on a b) (ontable b) (on c d) (ontable d)
    (clear a) (clear c)
    (handempty))
  (:goal (and (on a b) (on b c) (on c d))))
