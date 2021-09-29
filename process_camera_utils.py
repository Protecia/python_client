import cv2


def get_list_diff(l_new, l_old, thresh):
    new_copy = l_new[:]
    old_copy = l_old[:]
    for e_new in l_new:
        flag = False
        limit_pos = thresh
        for e_old in l_old:
            if e_new[0] == e_old[0]:
                diff_pos = (sum([abs(i-j) for i, j in zip(e_new[2], e_old[2])]))/(e_old[2][2]+e_old[2][3])*100
                if diff_pos < thresh:
                    flag = True
                    if diff_pos < limit_pos:
                        limit_pos = diff_pos
                        to_remove = (e_new, e_old)
        if flag:
            new_copy.remove(to_remove[0])
            try:
                old_copy.remove(to_remove[1])
                new_copy.remove(to_remove[0])
            except ValueError:
                pass
    return new_copy, old_copy


def read_write(rw, *args):
    if rw == 'r':
        im = cv2.imread(*args)
        return im
    if rw == 'w':
        r = cv2.imwrite(*args)
        return r


def EtoB(E):
    if E.is_set():
        return True
    else:
        return False