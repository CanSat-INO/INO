import { Component, Suspense, useMemo, useRef, type ReactNode, type MutableRefObject } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { Html, OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { TelemetryData } from '@cansat/shared';

interface Props { dataRef: MutableRefObject<TelemetryData | null>; state: number; attitudeValid: boolean }
interface CadMesh {
  name: string; color?: number[];
  attributes: { position: { array: number[] }; normal?: { array: number[] } };
  index: { array: number[] };
  brep_faces: { first: number; last: number; color?: number[] | null }[];
}

function Assembly({ dataRef, attitudeValid }: Props) {
  const raw = useLoader(THREE.FileLoader, '/models/cansat-assembly.json') as string;
  const ref = useRef<THREE.Group>(null);
  const target = useMemo(() => new THREE.Quaternion(), []);
  const euler = useMemo(() => new THREE.Euler(0, 0, 0, 'YXZ'), []);
  const model = useMemo(() => {
    const source = new THREE.Group();
    const { meshes } = JSON.parse(raw) as { meshes: CadMesh[] };
    for (const cad of meshes) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(cad.attributes.position.array, 3));
      geometry.setIndex(cad.index.array);
      if (cad.attributes.normal) geometry.setAttribute('normal', new THREE.Float32BufferAttribute(cad.attributes.normal.array, 3));
      else geometry.computeVertexNormals();
      const materialFor = (rgb?: number[] | null) => new THREE.MeshStandardMaterial({
        color: rgb ? new THREE.Color(rgb[0], rgb[1], rgb[2]) : '#b8c7d1',
        metalness: 0.12, roughness: 0.65, side: THREE.DoubleSide,
      });
      const materials = [materialFor(cad.color)];
      const colorIndices = new Map<string, number>();
      for (const face of cad.brep_faces) {
        let materialIndex = 0;
        if (face.color) {
          const key = face.color.join(',');
          if (!colorIndices.has(key)) colorIndices.set(key, materials.push(materialFor(face.color)) - 1);
          materialIndex = colorIndices.get(key)!;
        }
        const start = face.first * 3, count = (face.last - face.first + 1) * 3;
        const previous = geometry.groups[geometry.groups.length - 1];
        if (previous && previous.materialIndex === materialIndex && previous.start + previous.count === start) previous.count += count;
        else geometry.addGroup(start, count, materialIndex);
      }
      if (!cad.brep_faces.length) geometry.addGroup(0, cad.index.array.length, 0);
      const mesh = new THREE.Mesh(geometry, materials);
      mesh.name = cad.name;
      source.add(mesh);
    }
    // CAD uses Z-up; center the complete assembly at its attitude pivot.
    source.rotation.x = -Math.PI / 2;
    source.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(source);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    const scale = 3.6 / Math.max(size.x, size.y, size.z);
    if (!Number.isFinite(scale) || scale <= 0) throw new Error('Invalid CAD bounds');
    source.scale.setScalar(scale);
    source.position.copy(center).multiplyScalar(-scale);
    return source;
  }, [raw]);
  useFrame((_, delta) => {
    if (!ref.current) return;
    const d = dataRef.current;
    const angle = (value: number | undefined, fallback: number) => THREE.MathUtils.degToRad(
      attitudeValid && Number.isFinite(value) ? value! : fallback,
    );
    euler.set(angle(d?.orientationY, 0), angle(d?.orientationZ ?? d?.heading, 30), -angle(d?.orientationX, -15));
    target.setFromEuler(euler);
    ref.current.quaternion.slerp(target, 1 - Math.exp(-5 * delta));
  });
  return <group ref={ref}><primitive object={model} /></group>;
}

class ModelBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="stage-loading">CanSatモデルを読み込めません。ページを再読み込みしてください。</div> : this.props.children;
  }
}

export function CanSat3D(props: Props) {
  return <div className="digital-twin-canvas"><ModelBoundary>
    <Canvas camera={{ position: [4.8, 3.15, 4.8], fov: 41 }} dpr={[1, 1.5]}
      fallback={<div className="stage-loading">WebGLを有効にしてください。</div>}>
      <ambientLight intensity={1.5} />
      <directionalLight position={[5, 7, 4]} intensity={2.3} />
      <pointLight position={[-4, 2, -3]} intensity={1} color="#8fc8e8" />
      <Suspense fallback={<Html center>Loading CanSat…</Html>}><Assembly {...props} /></Suspense>
      <gridHelper args={[12, 24, '#263b52', '#172538']} position={[0, -2.4, 0]} />
      <OrbitControls makeDefault enablePan={false} minDistance={3.8} maxDistance={12} />
    </Canvas>
  </ModelBoundary></div>;
}
