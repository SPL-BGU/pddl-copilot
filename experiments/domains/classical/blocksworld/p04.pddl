;; 5 blocks: scattered to single tower
(define (problem bw-p04)
  (:domain blocksworld)
  (:objects a b c d e)
  (:init
    (ontable a) (ontable b) (ontable c) (on d e) (ontable e)
    (clear a) (clear b) (clear c) (clear d)
    (handempty))
  (:goal (and (on a b) (on b c) (on c d) (on d e))))
