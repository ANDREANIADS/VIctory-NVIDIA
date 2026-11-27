use bvh::{intersect, Ray};

fn control_node(kind: u32) -> [u32; 28] {
    let mut words = [0; 28];
    if kind < 4 {
        let indices = [[0, 1, 2], [1, 3, 2], [2, 3, 4], [2, 4, 0]][kind as usize];
        let vertices = [[0f32, 2., 5.], [2., -2., 5.], [-2., -2., 5.]];
        for (index, vertex) in indices.into_iter().zip(vertices) {
            words[3 * index..3 * index + 3].copy_from_slice(&vertex.map(f32::to_bits));
        }
        words[15] = 9 << (8 * kind);
    } else {
        words[..4].copy_from_slice(&[16, u32::MAX, u32::MAX, u32::MAX]);
        if kind == 4 {
            // FP16 coordinates of one box, from (-1,-1,4) through (1,1,6).
            words[4..7].copy_from_slice(&[0xbc00_bc00, 0x3c00_4400, 0x4600_3c00]);
        } else {
            words[4..10].copy_from_slice(&[-1f32, -1., 4., 1., 1., 6.].map(f32::to_bits));
        }
    }
    words
}

fn main() {
    for kind in 0..8 {
        let nodes = if kind < 6 {
            vec![("geometry", control_node(kind))]
        } else {
            vec![("zero", [0; 28]), ("pattern", std::array::from_fn(|i| i as u32 * 97 + 13))]
        };
        for (payload, words) in nodes {
            for (name, origin) in [("central", [0., 0., 0.]), ("offset", [9., 0., 0.])] {
                let ray = Ray::new(origin, [0., 0., 1.], 100.);
                for sort in [false, true] {
                    let result = intersect(&words, kind, &ray, sort);
                    // The controls assert a real triangle/box hit or miss for each revision.
                    if kind < 4 {
                        if name == "central" {
                            assert_eq!(f32::from_bits(result[0]) / f32::from_bits(result[1]), 5.);
                        } else {
                            assert_eq!(result, [0x7f80_0000, 0x3f80_0000, 0, 0]);
                        }
                    } else if kind < 6 {
                        let first = if name == "central" { 16 } else { u32::MAX };
                        assert_eq!(result, [first, u32::MAX, u32::MAX, u32::MAX]);
                    }
                    println!("{kind} {payload} {name} {sort} {:08x} {:08x} {:08x} {:08x}",
                             result[0], result[1], result[2], result[3]);
                }
            }
        }
    }
}
