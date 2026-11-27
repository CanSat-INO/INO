import ReactDOM from 'react-dom/client'
import App from './App'
import VirtualBench from './VirtualBench'
import './index.css'

// React StrictMode currently force-loses react-three-fiber's WebGL context
// during its development-only effect remount cycle.
ReactDOM.createRoot(document.getElementById('root')!).render(
  import.meta.env.DEV && new URLSearchParams(window.location.search).get('view') === 'virtual'
    ? <VirtualBench />
    : <App />,
)
