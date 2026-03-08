import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Provider } from 'react-redux'
import { store } from './store'
import Layout from './components/Layout/Layout'
import Dashboard from './pages/Dashboard/Dashboard'
import AccountList from './pages/Accounts/AccountList'
import AccountDetail from './pages/Accounts/AccountDetail'
import TopicTree from './pages/Taxonomy/TopicTree'
import TopicDetail from './pages/Taxonomy/TopicDetail'
import ReviewQueue from './pages/Taxonomy/ReviewQueue'
import Explorer from './pages/Explorer/Explorer'
import Starred from './pages/Starred/Starred'
import Settings from './pages/Settings/Settings'

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="accounts" element={<AccountList />} />
        <Route path="accounts/:id" element={<AccountDetail />} />
        <Route path="taxonomy" element={<TopicTree />} />
        <Route path="taxonomy/review" element={<ReviewQueue />} />
        <Route path="taxonomy/:id" element={<TopicDetail />} />
        <Route path="explorer" element={<Explorer />} />
        <Route path="starred" element={<Starred />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

function App() {
  return (
    <Provider store={store}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </Provider>
  )
}

export default App
